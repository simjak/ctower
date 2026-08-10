"""Real-Postgres acceptance for ConsoleViewGrant authority and encrypted custody."""

from __future__ import annotations

import hashlib
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.console_routes import ConsoleRuntime
from ctower_api.interface import create_app
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleBackendObservation,
    ConsoleOutputBatch,
    ConsolePolicy,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_HTTP_ACCEPTED = 202
_HTTP_CREATED = 201
_HTTP_FORBIDDEN = 403
_HTTP_OK = 200


@dataclass(slots=True)
class _Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class _BrowserContext:
    actor: Actor
    csrf_token: str
    session_token: str


class _Adapter:
    def __init__(self, observation: ConsoleBackendObservation, payload: bytes) -> None:
        self.observation = observation
        self.payload = payload

    def inspect(self, session_ref: ConsoleSessionRef) -> ConsoleBackendObservation:
        del session_ref
        return self.observation

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch:
        del session_ref
        payload = self.payload[after_cursor : after_cursor + maximum_bytes]
        return ConsoleOutputBatch(payload=payload, source_cursor=after_cursor + len(payload))


def _policy(*, grant_ttl_seconds: int = 300) -> ConsolePolicy:
    return ConsolePolicy(
        grant_ttl_seconds=grant_ttl_seconds,
        maximum_continuous_view_seconds=1_800,
        revocation_poll_seconds=5,
        decoded_chunk_bytes=16 * 1024,
        delivery_window_bytes=1024 * 1024,
        delivery_window_seconds=60,
        replay_window_bytes=1024 * 1024,
        replay_window_seconds=60,
        pending_bytes=256 * 1024,
        denial_limit=3,
        denial_window_seconds=300,
        suspension_seconds=900,
        policy_revision="console-phase1-r1",
    )


def test_console_view_grant_lifecycle_is_append_only_encrypted_and_fenced(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    ref = _recorded_session_ref(tenant)
    observation = _observation(ref)
    adapter = _Adapter(observation, b"console-phase1-acceptance-output\n")
    authority = PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=_policy())
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=bytes(range(32)),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=clock,
        sleeper=lambda _seconds: None,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = _browser_actor(tenant, now=now)

    allowance = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(
            session_ref=ref,
            sensitivity_class="restricted",
            loop_kind="standard",
        ),
    )
    assert not isinstance(allowance, RecordProblem)
    grant = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(grant, ConsoleViewGrant)
    assert grant.expires_at == now + timedelta(minutes=5)
    assert grant.maximum_uses == 1

    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    first_event = next(stream.events)
    assert b"event: chunk" in first_event
    assert b"console-phase1-acceptance-output" not in first_event

    renewed = viewer.mint_grant(browser, allowance.allowance_id, renewal=True)
    assert isinstance(renewed, ConsoleViewGrant)
    concurrent = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(concurrent, RecordProblem)
    assert concurrent.code == "console-stream-already-open"

    _assert_ciphertext_and_access_fact(tenant, b"console-phase1-acceptance-output")
    refusal = viewer.revoke_session(
        operator,
        ConsoleSessionRevocation(
            allowance_id=allowance.allowance_id,
            reason="acceptance revocation",
        ),
    )
    assert refusal is None
    closed = next(stream.events)
    assert b'"code":"revoked"' in closed
    with suppress(StopIteration):
        next(stream.events)

    after_revoke = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(after_revoke, RecordProblem)
    assert after_revoke.code == "console-session-revoked"
    _assert_immutable_grant(tenant, grant.grant_id)


def test_expiry_and_runtime_replacement_are_typed_refusals(tenant: TenantFixture) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    ref = _recorded_session_ref(tenant)
    adapter = _Adapter(_observation(ref), b"bounded output\n")
    authority = PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=_policy())
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=bytes(reversed(range(32))),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=clock,
        sleeper=lambda _seconds: None,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = _browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )
    assert not isinstance(allowance, RecordProblem)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)

    adapter.observation = _observation(ref, backend_incarnation="$replacement:2")
    fenced = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(fenced, RecordProblem)
    assert fenced.code == "console-incarnation-fenced"

    adapter.observation = _observation(ref)
    clock.now = now + timedelta(minutes=5)
    expired = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(expired, RecordProblem)
    assert expired.code == "console-grant-expired"


def test_console_output_reader_role_has_only_the_authored_custody_surface(
    tenant: TenantFixture,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        role = connection.execute(
            "SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = 'console_output_reader'"
        ).fetchone()
        membership = connection.execute(
            """
            SELECT 1
            FROM pg_auth_members AS membership
            JOIN pg_roles AS member ON member.oid = membership.member
            JOIN pg_roles AS target ON target.oid = membership.roleid
            WHERE member.rolname = 'ctower_svc' AND target.rolname = 'console_output_reader'
            """
        ).fetchone()
        grants = connection.execute(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'console_output_reader'
            ORDER BY table_name, privilege_type
            """
        ).fetchall()
    assert role == {"rolcanlogin": False, "rolinherit": False}
    assert membership is not None
    assert [(row["table_name"], row["privilege_type"]) for row in grants] == [
        ("console_output_objects", "SELECT")
    ]


def test_console_http_boundary_requires_exact_origin_cookie_csrf_and_secret_free_sse_url(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    ref = _recorded_session_ref(tenant)
    adapter = _Adapter(_observation(ref), b"browser-boundary-output\n")
    authority = PostgresConsoleAuthority(
        tenant.database.runtime_dsn,
        policy=_policy(grant_ttl_seconds=1),
    )
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-http-acceptance-kek").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=clock,
        sleeper=clock.sleep,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = _browser_context(tenant, now=now)
    allowance = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )
    assert not isinstance(allowance, RecordProblem)
    origin = "https://console.private.test"
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        console=ConsoleRuntime(viewer, origin),
    )
    refused_origin, refused_csrf, visible, minted, streamed = _console_http_responses(
        app, origin, browser, allowance.allowance_id
    )

    assert refused_origin.status_code == _HTTP_FORBIDDEN
    assert refused_origin.json()["code"] == "console-origin-refused"
    assert refused_csrf.status_code == _HTTP_FORBIDDEN
    assert refused_csrf.json()["code"] == "console-csrf-invalid"
    assert visible.status_code == _HTTP_OK
    assert visible.json()["sessions"][0]["console_session_id"] == str(allowance.allowance_id)
    assert minted.status_code == _HTTP_CREATED
    assert "grant" not in str(streamed.request.url.query)
    assert "session" not in str(streamed.request.url.query)
    assert streamed.status_code == _HTTP_OK
    assert streamed.headers["cache-control"] == "no-store"
    assert streamed.headers["x-accel-buffering"] == "no"
    assert "content-encoding" not in streamed.headers
    assert "event: chunk" in streamed.text
    assert "event: closed" in streamed.text
    assert '"code":"expired"' in streamed.text


def _console_http_responses(
    app: FastAPI,
    origin: str,
    browser: _BrowserContext,
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


def _recorded_session_ref(tenant: TenantFixture) -> ConsoleSessionRef:
    credential = secrets.token_urlsafe(32)
    seat_principal_id, ticket_id, session_id = _create_recorded_session(tenant, credential)
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
    runtime_attempt_id = uuid4()
    return ConsoleSessionRef(
        tenant_id=tenant.tenant_id,
        project_key="ctower",
        seat_principal_id=seat_principal_id,
        crew_name="engineer-console-p1",
        assignment_ticket_id=ticket_id,
        assignment_kind=str(assignment["assignment_kind"]),
        assignment_interval_sequence=cast(int, assignment["interval_sequence"]),
        recorded_work_session_id=session_id,
        runtime_attempt_id=runtime_attempt_id,
        runner_id="mission-control",
        runner_epoch=1,
        adapter_key="tmux-v1",
        opaque_backend_ref=f"crew:{session_id}",
        backend_incarnation=f"${session_id}:1",
    )


def _create_recorded_session(tenant: TenantFixture, credential: str) -> tuple[UUID, UUID, UUID]:
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        issued = cast(
            Response,
            client.post(
                "/v1/admin/seat-credentials",
                json={
                    "credential_digest": (
                        f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}"
                    ),
                    "credential_ref": "secret-ref:test/ctower/console-seat",
                    "display_name": f"Console Seat {uuid4().hex[:8]}",
                    "project_key": "ctower",
                    "scopes": ["capture", "transition", "evidence"],
                    "seat_key": f"console-seat-{uuid4().hex[:8]}",
                },
                headers=_headers(tenant.operator_credential),
            ),
        )
        assert issued.status_code == _HTTP_ACCEPTED, issued.text
        seat_principal_id = UUID(str(issued.json()["principal_id"]))
        created = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(seat_principal_id),
                    "priority": "P1",
                    "source": {"kind": "console-acceptance", "ref": f"gh437-{uuid4()}"},
                    "title": "Console Phase-1 acceptance target",
                },
                headers=_headers(tenant.operator_credential),
            ),
        )
        assert created.status_code == _HTTP_ACCEPTED, created.text
        ticket_id = UUID(str(created.json()["ticket"]["ticket_id"]))
        started = cast(
            Response,
            client.post(
                f"/v1/tickets/{ticket_id}/sessions",
                json={
                    "branch_ref": "feat/console-phase1-viewer",
                    "crew_name": "engineer-console-p1",
                    "harness_ref": "codex",
                    "model_ref": "gpt-5.6-sol",
                    "seat_key": "engineer",
                    "worktree_ref": "/srv/projects/ctower/.worktrees/console-p1",
                },
                headers=_headers(credential),
            ),
        )
        assert started.status_code == _HTTP_ACCEPTED, started.text
        session_id = UUID(str(started.json()["session_id"]))
    return seat_principal_id, ticket_id, session_id


def _browser_context(tenant: TenantFixture, *, now: datetime) -> _BrowserContext:
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
        telemetry=_telemetry(),
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
    return _BrowserContext(actor=actor, csrf_token=csrf_token, session_token=session_token)


def _browser_actor(tenant: TenantFixture, *, now: datetime) -> Actor:
    return _browser_context(tenant, now=now).actor


def _observation(
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


def _headers(credential: str) -> dict[str, str]:
    command_id = uuid4()
    return {
        **telemetry_headers(command_id),
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(command_id),
    }


def _telemetry() -> TelemetryContext:
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


def _assert_ciphertext_and_access_fact(tenant: TenantFixture, plaintext: bytes) -> None:
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


def _assert_immutable_grant(tenant: TenantFixture, grant_id: UUID) -> None:
    try:
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            connection.execute(
                "UPDATE console_view_grants SET policy_revision = 'tampered' WHERE grant_id = %s",
                (grant_id,),
            )
    except psycopg.errors.ObjectNotInPrerequisiteState:
        return
    raise AssertionError("console grant UPDATE unexpectedly succeeded")
