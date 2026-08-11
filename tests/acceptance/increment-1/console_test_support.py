"""Shared real-Postgres fixtures for the Console Phase-1 acceptance matrix."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleBackendObservation,
    ConsoleGlobalSwitchCommand,
    ConsoleOutputBatch,
    ConsolePolicy,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_HTTP_ACCEPTED = 202


@dataclass(slots=True)
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class BrowserContext:
    actor: Actor
    csrf_token: str
    session_token: str


class Adapter:
    def __init__(self, observation: ConsoleBackendObservation, payload: bytes) -> None:
        self.observation = observation
        self.payload = payload
        self.gap_reason: str | None = None
        self.gap_cursor = 0
        self.inspection_count = 0

    def inspect(self, session_ref: ConsoleSessionRef) -> ConsoleBackendObservation:
        del session_ref
        self.inspection_count += 1
        return self.observation

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch:
        del session_ref
        if self.gap_reason is not None:
            reason = self.gap_reason
            self.gap_reason = None
            return ConsoleOutputBatch(
                payload=b"",
                source_cursor=self.gap_cursor,
                gap=True,
                gap_reason=reason,
            )
        payload = self.payload[after_cursor : after_cursor + maximum_bytes]
        return ConsoleOutputBatch(payload=payload, source_cursor=after_cursor + len(payload))


def policy(
    *,
    grant_ttl_seconds: int = 300,
    revocation_poll_seconds: int = 4,
    pending_bytes: int = 256 * 1024,
    policy_revision: str = "console-phase1-r1",
) -> ConsolePolicy:
    return ConsolePolicy(
        grant_ttl_seconds=grant_ttl_seconds,
        maximum_continuous_view_seconds=1_800,
        revocation_poll_seconds=revocation_poll_seconds,
        decoded_chunk_bytes=16 * 1024,
        delivery_window_bytes=1024 * 1024,
        delivery_window_seconds=60,
        replay_window_bytes=1024 * 1024,
        replay_window_seconds=60,
        pending_bytes=pending_bytes,
        denial_limit=3,
        denial_window_seconds=300,
        suspension_seconds=900,
        policy_revision=policy_revision,
    )


def console_http_responses(
    app: FastAPI,
    origin: str,
    browser: BrowserContext,
    allowance_id: UUID,
) -> tuple[Response, Response, Response, Response, Response]:
    with TestClient(app, base_url=origin) as client:
        client.cookies.set("__Host-ctower_session", browser.session_token)
        client.cookies.set("__Host-ctower_csrf", browser.csrf_token)
        refused_origin = client.get(
            "/v1/console/sessions",
            headers={"Origin": "https://foreign.example", "X-Ctower-CSRF": browser.csrf_token},
        )
        refused_csrf = client.get(
            "/v1/console/sessions",
            headers={"Origin": origin, "X-Ctower-CSRF": "wrong-csrf"},
        )
        visible = client.get(
            "/v1/console/sessions",
            headers={"Origin": origin, "X-Ctower-CSRF": browser.csrf_token},
        )
        minted = client.post(
            f"/v1/console/sessions/{allowance_id}/grants",
            headers={"Origin": origin, "X-Ctower-CSRF": browser.csrf_token},
        )
        streamed = client.get(
            f"/v1/console/sessions/{allowance_id}/events",
            headers={"Origin": origin, "X-Ctower-CSRF": browser.csrf_token},
        )
    return refused_origin, refused_csrf, visible, minted, streamed


def console_setup(
    tenant: TenantFixture,
    now: datetime,
    *,
    clock: Clock | None = None,
    pending_bytes: int = 256 * 1024,
) -> tuple[
    ConsoleViewer,
    PostgresConsoleAuthority,
    Adapter,
    Actor,
    Actor,
    ConsoleSessionAllowance,
]:
    active_clock = clock or Clock(now)
    ref = recorded_session_ref(tenant)
    adapter = Adapter(observation(ref), b"console-authority-matrix-output\n")
    authority = PostgresConsoleAuthority(
        tenant.database.runtime_dsn, policy=policy(pending_bytes=pending_bytes)
    )
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-authority-matrix-kek").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=active_clock,
        sleeper=active_clock.sleep,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    return viewer, authority, adapter, operator, browser, allowance


def execute_service_fact(
    tenant: TenantFixture,
    statement: str,
    parameters: tuple[object, ...],
    *,
    use_admin: bool = False,
) -> None:
    dsn = tenant.database.admin_dsn if use_admin else tenant.database.runtime_dsn
    with psycopg.connect(dsn) as connection:
        if not use_admin:
            connection.execute("SET ROLE ctower_svc")
        connection.execute(statement, parameters)


def apply_first_open_change(
    change: str,
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    *,
    now: datetime,
) -> None:
    mutations = {
        "global": _enable_global_switch,
        "session": _revoke_console_session,
        "human-session": _revoke_human_session,
        "human-binding": _revoke_human_binding,
        "assignment": _release_assignment,
        "work-session": _close_work_session,
        "policy": _replace_policy,
    }
    mutations[change](tenant, viewer, authority, operator, browser, allowance, now)


def _enable_global_switch(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del tenant, authority, browser, allowance, now
    assert (
        viewer.set_global_switch(
            operator,
            ConsoleGlobalSwitchCommand(enabled=True, reason="pre-open containment"),
        )
        is None
    )


def _revoke_console_session(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del tenant, authority, browser, now
    assert (
        viewer.revoke_session(
            operator,
            ConsoleSessionRevocation(allowance.allowance_id, "pre-open revocation"),
        )
        is None
    )


def _revoke_human_session(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del viewer, authority, operator, allowance
    assert browser.human_session_id is not None
    execute_service_fact(
        tenant,
        """
        INSERT INTO human_session_revocations (session_id, tenant_id, reason, revoked_at)
        VALUES (%s, %s, 'pre-open revocation', %s)
        """,
        (browser.human_session_id, tenant.tenant_id, now),
    )


def _revoke_human_binding(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del viewer, authority, operator, allowance
    assert browser.human_binding_id is not None
    execute_service_fact(
        tenant,
        """
        INSERT INTO human_role_binding_revocations (
            binding_id, tenant_id, revoked_by, reason, revoked_at
        ) VALUES (%s, %s, %s, 'pre-open revocation', %s)
        """,
        (browser.human_binding_id, tenant.tenant_id, tenant.operator_id, now),
    )


def _release_assignment(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del viewer, operator
    ref = authority.session_ref(browser, allowance.allowance_id)
    assert isinstance(ref, ConsoleSessionRef)
    execute_service_fact(
        tenant,
        """
        UPDATE assignment_intervals SET released_at = %s
        WHERE ticket_id = %s AND assignment_kind = %s AND interval_sequence = %s
        """,
        (
            now + timedelta(seconds=1),
            ref.assignment_ticket_id,
            ref.assignment_kind,
            ref.assignment_interval_sequence,
        ),
    )


def _close_work_session(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del viewer, authority, operator, browser
    execute_service_fact(
        tenant,
        """
        INSERT INTO ticket_work_session_closures (
            session_id, tenant_id, outcome, duration_seconds, input_tokens,
            output_tokens, evidence_ref, closed_at, event_id
        )
        SELECT session_id, tenant_id, 'abandoned', 0, 0, 0,
            'console-pre-open-test', %s, event_id
        FROM ticket_work_sessions WHERE session_id = %s AND tenant_id = %s
        """,
        (now, allowance.recorded_work_session_id, tenant.tenant_id),
    )


def _replace_policy(
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    authority: PostgresConsoleAuthority,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    now: datetime,
) -> None:
    del tenant, viewer, operator, browser, allowance, now
    authority.policy = policy(policy_revision="console-phase1-r2")


def recorded_session_ref(tenant: TenantFixture, *, commander: bool = False) -> ConsoleSessionRef:
    credential = secrets.token_urlsafe(32)
    seat_principal_id, ticket_id, session_id = _create_recorded_session(
        tenant, credential, commander=commander
    )
    with psycopg.connect(tenant.database.runtime_dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        assignment = connection.execute(
            """
            SELECT assignment_kind, interval_sequence
            FROM assignment_intervals
            WHERE ticket_id = %s AND released_at IS NULL
            """,
            (ticket_id,),
        ).fetchone()
    assert assignment is not None
    return ConsoleSessionRef(
        tenant_id=tenant.tenant_id,
        project_key="ctower",
        seat_principal_id=seat_principal_id,
        crew_name="engineer-console-p1",
        assignment_ticket_id=ticket_id,
        assignment_kind=str(assignment["assignment_kind"]),
        assignment_interval_sequence=cast(int, assignment["interval_sequence"]),
        recorded_work_session_id=session_id,
        runtime_attempt_id=uuid4(),
        runner_id="mission-control",
        runner_epoch=1,
        adapter_key="tmux-v1",
        opaque_backend_ref=f"crew:{session_id}",
        backend_incarnation=f"${session_id}:1",
    )


def _create_recorded_session(
    tenant: TenantFixture, credential: str, *, commander: bool
) -> tuple[UUID, UUID, UUID]:
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        seat_principal_id = _create_seat(client, tenant, credential)
        ticket_id = _create_ticket(client, tenant, seat_principal_id)
        session_id = _start_session(client, credential, ticket_id)
    if not commander:
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            connection.execute(
                "UPDATE principals SET kind = 'agent' WHERE principal_id = %s",
                (seat_principal_id,),
            )
    return seat_principal_id, ticket_id, session_id


def _create_seat(client: TestClient, tenant: TenantFixture, credential: str) -> UUID:
    issued = client.post(
        "/v1/admin/seat-credentials",
        json={
            "credential_digest": f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
            "credential_ref": "secret-ref:test/ctower/console-seat",
            "display_name": f"Console Seat {uuid4().hex[:8]}",
            "project_key": "ctower",
            "scopes": ["capture", "transition", "evidence"],
            "seat_key": f"console-seat-{uuid4().hex[:8]}",
        },
        headers=headers(tenant.operator_credential),
    )
    assert issued.status_code == _HTTP_ACCEPTED, issued.text
    return UUID(str(issued.json()["principal_id"]))


def _create_ticket(client: TestClient, tenant: TenantFixture, seat_id: UUID) -> UUID:
    created = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(seat_id),
            "priority": "P1",
            "source": {"kind": "console-acceptance", "ref": f"gh437-{uuid4()}"},
            "title": "Console Phase-1 acceptance target",
        },
        headers=headers(tenant.operator_credential),
    )
    assert created.status_code == _HTTP_ACCEPTED, created.text
    return UUID(str(created.json()["ticket"]["ticket_id"]))


def _start_session(client: TestClient, credential: str, ticket_id: UUID) -> UUID:
    started = client.post(
        f"/v1/tickets/{ticket_id}/sessions",
        json={
            "branch_ref": "feat/console-phase1-viewer",
            "crew_name": "engineer-console-p1",
            "harness_ref": "codex",
            "model_ref": "gpt-5.6-sol",
            "seat_key": "engineer",
            "worktree_ref": "/srv/projects/ctower/.worktrees/console-p1",
        },
        headers=headers(credential),
    )
    assert started.status_code == _HTTP_ACCEPTED, started.text
    return UUID(str(started.json()["session_id"]))


def browser_context(tenant: TenantFixture, *, now: datetime) -> BrowserContext:
    record = PostgresRecord(tenant.database.runtime_dsn)
    binding = record.human_identity.bind_role(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"Console Viewer {uuid4().hex[:8]}",
            oidc_issuer="https://console-idp.example.test",
            oidc_subject=f"viewer-{uuid4()}",
            project_keys=("ctower",),
            role="viewer",
        ),
        request_digest=hashlib.sha256(uuid4().bytes).digest(),
        now=now,
        telemetry=telemetry(),
    )
    assert not isinstance(binding, RecordProblem)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    record.human_identity.issue_session(
        binding.principal_id,
        tenant.tenant_id,
        binding.binding_id,
        "viewer",
        session_digest=hashlib.sha256(session_token.encode()).digest(),
        csrf_digest=hashlib.sha256(csrf_token.encode()).digest(),
        now=now,
        ttl_seconds=3600,
    )
    actor = record.human_identity.actor_for_session(
        hashlib.sha256(session_token.encode()).digest(), now=now
    )
    assert actor is not None and not isinstance(actor, RecordProblem)
    return BrowserContext(actor=actor, csrf_token=csrf_token, session_token=session_token)


def browser_actor(tenant: TenantFixture, *, now: datetime) -> Actor:
    return browser_context(tenant, now=now).actor


def observation(
    ref: ConsoleSessionRef, *, backend_incarnation: str | None = None
) -> ConsoleBackendObservation:
    return ConsoleBackendObservation(
        project_key=ref.project_key,
        runtime_attempt_id=ref.runtime_attempt_id,
        runner_id=ref.runner_id,
        runner_epoch=ref.runner_epoch,
        opaque_backend_ref=ref.opaque_backend_ref,
        backend_incarnation=backend_incarnation or ref.backend_incarnation,
    )


def headers(credential: str) -> dict[str, str]:
    command_id = uuid4()
    return {
        **telemetry_headers(command_id),
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(command_id),
    }


def telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=0,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="acceptance",
        actor_id="acceptance",
        command_id=command_id,
    )


def assert_ciphertext_and_access_fact(tenant: TenantFixture, plaintext: bytes) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        output = connection.execute(
            "SELECT ciphertext, wrapped_data_key, data_key_reference FROM console_output_objects"
        ).fetchone()
        access_count = connection.execute(
            "SELECT count(*) AS count FROM console_output_access_facts"
        ).fetchone()
    assert output is not None and access_count is not None
    assert plaintext not in bytes(cast(bytes, output["ciphertext"]))
    assert plaintext not in bytes(cast(bytes, output["wrapped_data_key"]))
    assert output["data_key_reference"] is not None
    assert access_count["count"] == 1


def assert_immutable_grant(tenant: TenantFixture, grant_id: UUID) -> None:
    try:
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            connection.execute(
                "UPDATE console_view_grants SET policy_revision = 'tampered' WHERE grant_id = %s",
                (grant_id,),
            )
    except psycopg.errors.ObjectNotInPrerequisiteState:
        return
    raise AssertionError("console grant UPDATE unexpectedly succeeded")
