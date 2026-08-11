"""Real-Postgres acceptance for ConsoleViewGrant authority and encrypted custody."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Generator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
import pytest
from console_test_support import (
    Adapter as _Adapter,
)
from console_test_support import (
    Clock as _Clock,
)
from console_test_support import (
    apply_first_open_change as _apply_first_open_change,
)
from console_test_support import (
    assert_ciphertext_and_access_fact as _assert_ciphertext_and_access_fact,
)
from console_test_support import (
    assert_immutable_grant as _assert_immutable_grant,
)
from console_test_support import (
    browser_actor as _browser_actor,
)
from console_test_support import (
    browser_context as _browser_context,
)
from console_test_support import (
    console_http_responses as _console_http_responses,
)
from console_test_support import (
    console_setup as _console_setup,
)
from console_test_support import (
    observation as _observation,
)
from console_test_support import (
    policy as _policy,
)
from console_test_support import (
    recorded_session_ref as _recorded_session_ref,
)
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_api.console_routes import ConsoleRuntime
from ctower_api.interface import create_app
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

_HTTP_ACCEPTED = 202
_HTTP_CREATED = 201
_HTTP_FORBIDDEN = 403
_HTTP_OK = 200
_DENIAL_LIMIT = 3


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


def test_active_runtime_replacement_closes_typed_within_the_poll_bound(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    viewer, authority, adapter, _operator, browser, allowance = _console_setup(
        tenant, now, clock=clock
    )
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b"event: chunk" in next(stream.events)
    ref = authority.session_ref(browser, allowance.allowance_id)
    assert isinstance(ref, ConsoleSessionRef)
    replaced_at = clock.now
    adapter.observation = _observation(ref, backend_incarnation="$replacement:active")

    closed = next(stream.events)
    assert b'"code":"fenced"' in closed
    with suppress(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT code, closed_at FROM console_stream_closes WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
    assert row == {"code": "fenced", "closed_at": replaced_at}
    assert cast(datetime, row["closed_at"]) <= replaced_at + timedelta(seconds=5)


def test_active_stream_expiry_closes_at_the_exact_absolute_deadline(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    ref = _recorded_session_ref(tenant)
    adapter = _Adapter(_observation(ref), b"exact-expiry-output\n")
    authority = PostgresConsoleAuthority(
        tenant.database.runtime_dsn,
        policy=_policy(grant_ttl_seconds=3),
    )
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-exact-expiry-kek").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=clock,
        sleeper=clock.sleep,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = _browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )
    assert not isinstance(allowance, RecordProblem)
    grant = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(grant, ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b"event: chunk" in next(stream.events)
    assert b'"code":"expired"' in next(stream.events)
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT closed_at FROM console_stream_closes WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
    assert row == {"closed_at": grant.expires_at}


@pytest.mark.parametrize("target_state", ["commander", "disabled"])
def test_ineligible_target_is_absent_before_any_console_fact(
    tenant: TenantFixture,
    target_state: str,
) -> None:
    now = datetime.now(UTC)
    ref = _recorded_session_ref(tenant, commander=target_state == "commander")
    if target_state == "disabled":
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            connection.execute(
                "UPDATE principals SET disabled = true WHERE principal_id = %s",
                (ref.seat_principal_id,),
            )
    viewer = ConsoleViewer(
        PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=_policy()),
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        _Adapter(_observation(ref), b"must-not-be-visible"),
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"commander-target-refusal").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)

    refused = viewer.allow_session(
        operator,
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-session-join-stale"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        count = connection.execute(
            "SELECT count(*) AS count FROM console_session_allows"
        ).fetchone()
    assert count == {"count": 0}


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [
        ("global", "console-globally-disabled"),
        ("session", "console-session-revoked"),
        ("human-session", "console-reauthentication-required"),
        ("human-binding", "console-reauthentication-required"),
        ("assignment", "console-session-revoked"),
        ("work-session", "console-session-revoked"),
        ("policy", "console-policy-stale"),
    ],
)
def test_first_open_rechecks_current_authority_without_consuming_the_grant(
    tenant: TenantFixture,
    change: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    viewer, authority, _adapter, operator, browser, allowance = _console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)

    _apply_first_open_change(
        change,
        tenant,
        viewer,
        authority,
        operator,
        browser,
        allowance,
        now=now,
    )

    refused = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(refused, RecordProblem)
    assert refused.code == expected_code
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        count = connection.execute("SELECT count(*) AS count FROM console_stream_opens").fetchone()
    assert count == {"count": 0}


def test_three_persisted_denials_suspend_for_the_full_fifteen_minutes(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = _Clock(now)
    viewer, authority, adapter, _operator, browser, allowance = _console_setup(
        tenant, now, clock=clock
    )
    ref = cast(ConsoleSessionRef, authority.session_ref(browser, allowance.allowance_id))
    adapter.observation = _observation(ref, backend_incarnation="$denied:2")

    for _index in range(_DENIAL_LIMIT):
        denied = viewer.mint_grant(browser, allowance.allowance_id)
        assert isinstance(denied, RecordProblem)
        assert denied.code == "console-incarnation-fenced"

    adapter.observation = _observation(ref)
    suspended = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(suspended, RecordProblem)
    assert suspended.code == "console-actor-suspended"
    clock.now = now + timedelta(seconds=899)
    still_suspended = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(still_suspended, RecordProblem)
    assert still_suspended.code == "console-actor-suspended"
    clock.now = now + timedelta(seconds=900)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT denial_count, suspended_at, expires_at
            FROM console_view_suspensions
            """
        ).fetchone()
    assert row is not None
    assert row["denial_count"] == _DENIAL_LIMIT
    assert row["suspended_at"] == now
    assert row["expires_at"] == now + timedelta(minutes=15)


def test_renew_before_use_replaces_the_only_claimable_grant(tenant: TenantFixture) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = _console_setup(tenant, now)
    original = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(original, ConsoleViewGrant)
    replacement = viewer.mint_grant(browser, allowance.allowance_id, renewal=True)
    assert isinstance(replacement, ConsoleViewGrant)

    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)

    assert not isinstance(stream, RecordProblem)
    assert stream.lease.grant.grant_id == replacement.grant_id
    assert stream.lease.grant.grant_id != original.grant_id


def test_source_truncation_starts_a_new_generation_without_cursor_collision(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = _console_setup(tenant, now)
    adapter.payload = b"first"
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b"event: chunk" in next(stream.events)

    adapter.gap_reason = "source-truncated"
    adapter.gap_cursor = 0
    adapter.payload = b"again"
    assert b'"reason":"source_truncated"' in next(stream.events)
    assert b"event: chunk" in next(stream.events)
    cast(Generator[bytes, None, None], stream.events).close()

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT source_cursor, source_generation
            FROM console_output_objects ORDER BY source_position
            """
        ).fetchall()
    assert rows == [
        {"source_cursor": 5, "source_generation": 1},
        {"source_cursor": 5, "source_generation": 2},
    ]


def test_reconnect_replays_a_committed_truncation_gap_before_the_new_generation(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = _console_setup(tenant, now)
    adapter.payload = b"first"
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    original = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(original, RecordProblem)
    first = next(original.events)
    first_cursor = int(first.splitlines()[0].removeprefix(b"id: "))
    cast(Generator[bytes, None, None], original.events).close()

    store = PostgresConsoleOutputStore(tenant.database.runtime_dsn)
    gap_cursor = store.record_gap(
        allowance.allowance_id,
        tenant.tenant_id,
        0,
        2,
        "source_truncated",
        now=now,
    )
    adapter.payload = b"again"
    assert isinstance(
        viewer.mint_grant(browser, allowance.allowance_id, renewal=True), ConsoleViewGrant
    )
    reconnect = viewer.open_stream(
        browser,
        allowance.allowance_id,
        last_event_id=first_cursor,
    )
    assert not isinstance(reconnect, RecordProblem)

    gap = next(reconnect.events)
    chunk = next(reconnect.events)

    assert gap.startswith(f"id: {gap_cursor}\nevent: gap\n".encode())
    assert b'"next_cursor":' + str(gap_cursor).encode() in gap
    assert b'"reason":"source_truncated"' in gap
    assert b"event: chunk" in chunk
    assert int(chunk.splitlines()[0].removeprefix(b"id: ")) > gap_cursor
    cast(Generator[bytes, None, None], reconnect.events).close()


def test_console_output_reader_role_has_only_the_authored_custody_surface(
    tenant: TenantFixture,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        role = connection.execute(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                rolreplication, rolbypassrls, rolconnlimit
            FROM pg_roles WHERE rolname = 'console_output_reader'
            """
        ).fetchone()
        memberships = connection.execute(
            """
            SELECT member.rolname AS member_name, granted.rolname AS granted_name,
                membership.admin_option
            FROM pg_auth_members AS membership
            JOIN pg_roles AS member ON member.oid = membership.member
            JOIN pg_roles AS granted ON granted.oid = membership.roleid
            WHERE member.rolname = 'console_output_reader'
               OR granted.rolname = 'console_output_reader'
            ORDER BY member.rolname, granted.rolname
            """
        ).fetchall()
        settings = connection.execute(
            """
            SELECT 1 FROM pg_db_role_setting AS setting
            JOIN pg_roles AS role ON role.oid = setting.setrole
            WHERE role.rolname = 'console_output_reader'
            """
        ).fetchall()
        grants = connection.execute(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'console_output_reader'
            ORDER BY table_name, privilege_type
            """
        ).fetchall()
    assert role == {
        "rolcanlogin": False,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolinherit": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "rolconnlimit": -1,
    }
    assert memberships == [
        {
            "member_name": "ctower_admin",
            "granted_name": "console_output_reader",
            "admin_option": False,
        }
    ]
    assert settings == []
    assert [(row["table_name"], row["privilege_type"]) for row in grants] == [
        ("console_output_access_facts", "SELECT"),
        ("console_output_objects", "SELECT"),
        ("console_output_recovery_facts", "INSERT"),
    ]
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_svc")
        connection.execute("SELECT ciphertext FROM console_output_objects LIMIT 1")
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE console_output_reader")


def test_custody_failure_emits_a_typed_gap_and_close(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = _console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b"event: chunk" in next(stream.events)

    def fail_reader(*_args: object, **_kwargs: object) -> RecordProblem:
        return RecordProblem(
            code="console-output-unavailable",
            detail="Injected custody outage.",
            status=503,
            title="Console output unavailable",
        )

    monkeypatch.setattr(PostgresConsoleOutputStore, "outputs_after", fail_reader)
    gap = next(stream.events)
    closed = next(stream.events)
    assert b'"reason":"cursor_unavailable"' in gap
    assert b'"code":"output_unavailable"' in closed
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_output_access_facts) AS access_count,
                (SELECT count(*) FROM console_output_gap_facts
                 WHERE reason = 'cursor_unavailable') AS gap_count,
                (SELECT code FROM console_stream_closes
                 WHERE stream_id = %s) AS close_code
            """,
            (stream.lease.stream_id,),
        ).fetchone()
    assert facts == {"access_count": 1, "gap_count": 1, "close_code": "output_unavailable"}


def test_reader_failure_preserves_the_committed_access_attempt(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = _console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)

    def fail_after_access(
        _store: PostgresConsoleOutputStore, _access_id: UUID, *, now: datetime
    ) -> dict[str, object] | None:
        del now
        raise psycopg.OperationalError("injected reader failure")

    monkeypatch.setattr(PostgresConsoleOutputStore, "_recover_object", fail_after_access)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b'"reason":"cursor_unavailable"' in next(stream.events)
    assert b'"code":"output_unavailable"' in next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT access_kind, outcome
            FROM console_output_access_facts
            ORDER BY accessed_at, access_id
            """
        ).fetchall()
    assert facts == [{"access_kind": "open", "outcome": "authorized"}]


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
    origin = "https://100.84.252.114:8443"
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
    validator = Draft202012Validator(
        json.loads(
            (
                Path(__file__).parents[3]
                / "contracts/domain/console/console-stream-event.schema.json"
            ).read_text(encoding="utf-8")
        )
    )
    for line in streamed.text.splitlines():
        if line.startswith("data: "):
            validator.validate(json.loads(line.removeprefix("data: ")))
