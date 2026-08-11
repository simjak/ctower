"""Real-Postgres proofs that authority refusal precedes runtime inspection."""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from console_test_support import (
    Adapter,
    browser_actor,
    console_setup,
    execute_service_fact,
    observation,
    policy,
    recorded_session_ref,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleEventStream,
    ConsoleSessionAllowCommand,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()


def test_non_operator_allowance_refuses_before_adapter_inspection(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    adapter = Adapter(observation(ref), b"must-not-be-read")
    viewer = _viewer(tenant, adapter, now)

    refused = viewer.allow_session(
        browser_actor(tenant, now=now),
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-allowlist-refused"
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("actor_state", ["commander", "foreign-project"])
def test_ineligible_actor_mint_refuses_before_adapter_inspection(
    tenant: TenantFixture,
    actor_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    actor = (
        replace(browser, kind=PrincipalKind.COMMANDER)
        if actor_state == "commander"
        else replace(browser, project_grants=frozenset({"foreign-project"}))
    )
    adapter.inspection_count = 0

    refused = viewer.mint_grant(actor, allowance.allowance_id)

    assert isinstance(refused, RecordProblem)
    assert refused.code == (
        "console-role-refused" if actor_state == "commander" else "console-project-refused"
    )
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("authority_state", ["suspended", "revoked"])
def test_inactive_session_is_absent_and_mint_refuses_without_adapter_inspection(
    tenant: TenantFixture,
    authority_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, operator, browser, allowance = console_setup(tenant, now)
    if authority_state == "revoked":
        assert (
            viewer.revoke_session(
                operator,
                ConsoleSessionRevocation(allowance.allowance_id, "preflight refusal proof"),
            )
            is None
        )
    else:
        execute_service_fact(
            tenant,
            """
            INSERT INTO console_view_suspensions (
                suspension_id, tenant_id, actor_principal_id, denial_count,
                reason, suspended_at, expires_at
            ) VALUES (%s, %s, %s, 3, 'preflight refusal proof', %s, %s)
            """,
            (uuid4(), tenant.tenant_id, browser.principal_id, now, now + timedelta(minutes=15)),
        )
    adapter.inspection_count = 0

    assert viewer.visible_sessions(browser) == ()
    refused = viewer.mint_grant(browser, allowance.allowance_id)

    assert isinstance(refused, RecordProblem)
    assert refused.code == (
        "console-actor-suspended" if authority_state == "suspended" else "console-session-revoked"
    )
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("grant_state", ["missing", "used"])
def test_unclaimable_grant_refuses_before_adapter_inspection(
    tenant: TenantFixture,
    grant_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    if grant_state == "used":
        assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
        opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
        assert isinstance(opened, ConsoleEventStream)
        next(opened.events)
        cast(Generator[bytes, None, None], opened.events).close()
    adapter.inspection_count = 0

    refused = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-grant-unavailable"
    assert adapter.inspection_count == 0


def _viewer(tenant: TenantFixture, adapter: Adapter, now: datetime) -> ConsoleViewer:
    return ConsoleViewer(
        PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy()),
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-authority-preflight").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
