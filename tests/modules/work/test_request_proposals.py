"""RED-first real-PostgreSQL boundary for Request-maintenance proposals."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import cast
from uuid import UUID

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import _request_proposal_read_sql as proposal_read
from ctower_kernel.work.request_proposals import (
    PostgresRequestProposals,
    RequestMaintenanceProposalAppend,
    RequestProposals,
    _relation_shape_refusal,
)
from modules.migration._postgres import Database, isolated_database

__all__: tuple[str, ...] = ()
EXPECTED_RETRY_ATTEMPTS = 3


@pytest.fixture
def proposal_database() -> Iterator[Database]:
    """Use the kernel's real fresh-apply PostgreSQL fixture without skips."""

    yield from isolated_database()


def test_fresh_apply_installs_separate_append_only_proposal_facts(
    proposal_database: Database,
) -> None:
    with psycopg.connect(proposal_database.admin_dsn) as connection:
        tables = connection.execute(
            """
            SELECT to_regclass('public.request_maintenance_proposals'),
                   to_regclass('public.request_maintenance_proposal_evidence'),
                   to_regclass('public.request_maintenance_proposal_decisions')
            """
        ).fetchone()

    assert tables == (
        "request_maintenance_proposals",
        "request_maintenance_proposal_evidence",
        "request_maintenance_proposal_decisions",
    )


def test_partial_and_self_relations_refuse_before_postgresql_constraints() -> None:
    target_id = UUID("00000000-0000-7000-8000-000000000101")
    command = RequestMaintenanceProposalAppend(
        client_command_id=UUID("00000000-0000-7000-8000-000000000102"),
        project_key="ctower",
        kind="keep",
        basis="recorded-evidence",
        target_request_id=target_id,
        target_expected_version=1,
        target_text="Exact Request text.",
        source_record_position=1,
        evidence=(),
    )
    partial = replace(command, related_request_id=target_id)
    self_relation = replace(
        command,
        kind="duplicate",
        related_request_id=target_id,
        related_expected_version=1,
        related_text=command.target_text,
    )
    valid_relation = replace(
        self_relation,
        related_request_id=UUID("00000000-0000-7000-8000-000000000103"),
    )

    assert isinstance(_relation_shape_refusal(partial), RecordProblem)
    assert isinstance(_relation_shape_refusal(self_relation), RecordProblem)
    assert _relation_shape_refusal(valid_relation) is None


def test_proposal_read_retries_only_transient_failures_with_bounded_backoff_and_logs_exhaustion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def fail() -> object:
        nonlocal attempts
        attempts += 1
        raise psycopg.OperationalError("database connection unavailable")

    with caplog.at_level(logging.ERROR):
        outcome = proposal_read._read_with_retry(
            fail,
            sleep=sleeps.append,
            monotonic=lambda: 0.0,
            jitter=lambda ceiling: ceiling,
        )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "proposal-read-retry-exhausted"
    assert attempts == EXPECTED_RETRY_ATTEMPTS
    assert sleeps == [0.05, 0.1]
    assert "Request proposal database read retry policy exhausted" in caplog.text


def test_proposal_read_does_not_retry_terminal_database_failures() -> None:
    attempts = 0

    def fail() -> object:
        nonlocal attempts
        attempts += 1
        raise psycopg.errors.UndefinedTable("schema contract is unavailable")

    outcome = proposal_read._read_with_retry(
        fail,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        jitter=lambda ceiling: ceiling,
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "proposal-read-database-error"
    assert attempts == 1


def test_proposal_read_dsn_has_explicit_connection_and_statement_deadlines() -> None:
    bounded = conninfo_to_dict(proposal_read._bounded_dsn("dbname=ctower host=127.0.0.1"))

    assert bounded["connect_timeout"] == "2"
    assert "statement_timeout=5000" in cast(str, bounded["options"])


def test_proposal_read_exhaustion_emits_the_typed_metric_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problem = RecordProblem(
        code="proposal-read-retry-exhausted",
        detail="Request proposal database read retry policy exhausted",
        status=503,
        title="Request proposal unavailable",
    )
    store = PostgresRequestProposals("dbname=unused")
    monkeypatch.setattr(store, "list", lambda *_args, **_kwargs: problem)
    telemetry = _Telemetry()
    actor = Actor(UUID(int=1), UUID(int=2), PrincipalKind.OPERATOR)
    context = _telemetry(actor)

    outcome = RequestProposals(store, telemetry=telemetry).list(actor, telemetry=context)

    assert outcome is problem
    assert telemetry.records == [
        ("work.request-proposal.list", "error", "proposal-read-retry-exhausted")
    ]


class _Telemetry:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, str]] = []

    def emit(
        self,
        name: str,
        context: TelemetryContext,
        *,
        outcome: str,
        reason: str,
    ) -> None:
        del context
        self.records.append((name, outcome, reason))


def _telemetry(actor: Actor) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(UUID(int=3)),
        causation_id=str(UUID(int=3)),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(UUID(int=3)),
    )
