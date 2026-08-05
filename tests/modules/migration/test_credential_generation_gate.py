"""Real PostgreSQL tests for the credential-path generation gate (gh#259).

`record/_credential_sql.py` resolves bearer authority (`actor_for_credential`, line 49) and
appends/reads seat-credential state (`issue_seat_credential` via `_append_issuance` at lines
267/488, `revoke_seat_credential` via `_append_revocation` at line 561) against tables migration
0039 creates. Each of the three public entry points below reaches one of those four call sites on
a database ledgered only through 0038 — the generation immediately before 0039 — and must refuse
by name instead of letting `psycopg.errors.UndefinedTable` propagate from a protected read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, _credential_sql
from ctower_kernel.record.credentials import (
    CredentialScope,
    SeatCredentialIssue,
    SeatCredentialRevocation,
)
from ctower_kernel.telemetry import TelemetryContext

from ._ledger_support import LEDGERED_TERMINAL, install_ledger_through
from ._postgres import Database

__all__: tuple[str, ...] = ()

_REQUIRED_GENERATION = "0039"
_SERVICE_UNAVAILABLE = 503


@pytest.fixture
def pre_generation_database(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> Database:
    """A database ledgered only through 0035 — the generation the 2026-08-03 live incident hit.

    Any generation before 0039 reproduces the recurrence point; reusing the exact incident
    terminal ties this proof to the documented failure rather than an arbitrary cutoff.
    """

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    _seed_tenant_and_operator(migration_database)
    return migration_database


def _seed_tenant_and_operator(database: Database) -> None:
    now = datetime.now(UTC)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
            (database.tenant_id, "ctower", "Ctower", now),
        )
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'operator', 'Migration Operator', false, %s)
            """,
            (database.operator_id, database.tenant_id, now),
        )


def _operator(database: Database) -> Actor:
    return Actor(database.operator_id, database.tenant_id, PrincipalKind.OPERATOR)


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )


def _assert_generation_refusal(outcome: object) -> None:
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "credential-authentication-unavailable"
    assert outcome.status == _SERVICE_UNAVAILABLE
    assert _REQUIRED_GENERATION in outcome.detail


def test_actor_for_credential_refuses_by_name_before_generation_0039(
    pre_generation_database: Database,
) -> None:
    """Line 49: the LEFT JOIN seat_credential_issuances read."""

    outcome = _credential_sql.actor_for_credential(pre_generation_database.runtime_dsn, b"0" * 32)

    _assert_generation_refusal(outcome)


def test_issue_seat_credential_refuses_by_name_before_generation_0039(
    pre_generation_database: Database,
) -> None:
    """Lines 267 and 488: the issuance INSERT and the issuance-conflict SELECT.

    Both live inside `_append_issuance`, reached only once the gate at its top lets a
    call through, so one call proves both named lines refuse together.
    """

    command = SeatCredentialIssue(
        client_command_id=uuid4(),
        credential_digest=b"1" * 32,
        credential_ref="test-credential-ref",
        display_name="Generation Gate Prober",
        project_key="ctower",
        scopes=(CredentialScope.CAPTURE,),
        seat_key="ctower-generation-gate-prober",
    )

    outcome = _credential_sql.issue_seat_credential(
        pre_generation_database.runtime_dsn,
        _operator(pre_generation_database),
        command,
        request_digest=b"2" * 32,
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    _assert_generation_refusal(outcome)


def test_revoke_seat_credential_refuses_by_name_before_generation_0039(
    pre_generation_database: Database,
) -> None:
    """Line 561: the locked-issuance read `_append_revocation` performs before revoking."""

    command = SeatCredentialRevocation(
        client_command_id=uuid4(),
        credential_id=uuid4(),
        reason="generation gate probe",
    )

    outcome = _credential_sql.revoke_seat_credential(
        pre_generation_database.runtime_dsn,
        _operator(pre_generation_database),
        command,
        request_digest=b"3" * 32,
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    _assert_generation_refusal(outcome)
