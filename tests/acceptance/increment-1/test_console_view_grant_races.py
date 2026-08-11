"""Real-Postgres concurrency, replay, backpressure, and custody races for Console Phase 1."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from threading import Barrier
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from console_test_support import (
    Adapter,
    apply_first_open_change,
    browser_actor,
    console_setup,
    observation,
    policy,
    recorded_session_ref,
)
from jsonschema import Draft202012Validator
from psycopg.rows import dict_row
from starlette.types import Send
from support.tenant_fixture import TenantFixture

from ctower_api.console_adapter import ConsoleBackendRegistration, TmuxConsoleAdapter
from ctower_api.console_streaming import console_streaming_response
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleEventStream,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()
_MAX_CLOSE_SECONDS = 5
_LIVE_IDENTITY_INVOCATIONS = 2


def _replacement_racing_adapter(
    ref: ConsoleSessionRef,
    tmp_path: Path,
    replacement_kind: str,
    armed: list[bool],
) -> TmuxConsoleAdapter:
    log = tmp_path / "console.log"
    log.write_bytes(b"replacement-race-output")
    identity = log.stat()
    registration = ConsoleBackendRegistration(
        ref.opaque_backend_ref,
        "mc-engineer-console-p1:0.0",
        log,
        ref.runtime_attempt_id,
        ref.runner_id,
        ref.runner_epoch,
        identity.st_dev,
        identity.st_ino,
    )
    registrations = {ref.opaque_backend_ref: registration}
    replacement_log = tmp_path / "replacement.log"
    replacement_log.write_bytes(b"untrusted replacement bytes")
    armed_calls = 0

    def runner(command: tuple[str, ...]) -> CompletedProcess[str]:
        nonlocal armed_calls
        stdout = (
            f"{ref.project_key}\n"
            if command[-2:] == ("-v", "@project")
            else ref.backend_incarnation.replace(":", "\t", 1) + "\n"
        )
        if armed[0]:
            armed_calls += 1
            if armed_calls == _LIVE_IDENTITY_INVOCATIONS:
                if replacement_kind == "registry":
                    registrations[ref.opaque_backend_ref] = replace(
                        registration, runtime_attempt_id=uuid4()
                    )
                else:
                    source = replacement_log
                    if replacement_kind == "hard-link":
                        source = tmp_path / "replacement-link.log"
                        source.hardlink_to(replacement_log)
                    source.replace(log)
        return CompletedProcess(command, 0, stdout=stdout, stderr="")

    return TmuxConsoleAdapter(
        tmux_binary="tmux",
        socket_name="mc",
        allowed_log_root=tmp_path,
        registration_reader=registrations.get,
        command_runner=runner,
    )


def test_parallel_stream_claim_has_exactly_one_real_postgres_winner(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    barrier = Barrier(2)

    def claim() -> ConsoleEventStream | RecordProblem:
        barrier.wait()
        return viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result() for future in (executor.submit(claim), executor.submit(claim))]
    streams = [outcome for outcome in outcomes if isinstance(outcome, ConsoleEventStream)]
    refusals = [outcome for outcome in outcomes if isinstance(outcome, RecordProblem)]
    assert len(streams) == 1
    assert [refusal.code for refusal in refusals] == ["console-stream-already-open"]
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM console_stream_opens").fetchone()
    assert count == (1,)
    cast(Generator[bytes, None, None], streams[0].events).close()


def test_parallel_initial_grant_mint_has_one_real_postgres_winner(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    barrier = Barrier(2)

    def mint() -> ConsoleViewGrant | RecordProblem:
        barrier.wait()
        return viewer.mint_grant(browser, allowance.allowance_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result() for future in (executor.submit(mint), executor.submit(mint))]

    assert len([outcome for outcome in outcomes if isinstance(outcome, ConsoleViewGrant)]) == 1
    refusals = [outcome.code for outcome in outcomes if isinstance(outcome, RecordProblem)]
    assert refusals == ["console-grant-already-current"]
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM console_view_grants").fetchone()
    assert count == (1,)


@pytest.mark.parametrize("replacement_kind", ["registry", "rename", "hard-link"])
def test_backend_replacement_between_inspection_and_read_persists_zero_bytes(
    tenant: TenantFixture,
    tmp_path: Path,
    replacement_kind: str,
) -> None:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    armed = [False]
    adapter = _replacement_racing_adapter(ref, tmp_path, replacement_kind, armed)
    viewer = ConsoleViewer(
        PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy()),
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"registry-read-race").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)

    armed[0] = True
    closed = next(stream.events)
    assert b'"code":"fenced"' in closed
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_output_objects) AS objects,
                (SELECT count(*) FROM console_output_access_facts) AS accesses
            """
        ).fetchone()
    assert facts == (0, 0)


@pytest.mark.parametrize("target_change", ["disabled", "commander"])
@pytest.mark.parametrize("decision", ["discovery", "mint", "renewal", "open", "active"])
def test_target_authority_is_current_at_every_post_allowance_decision(
    tenant: TenantFixture,
    target_change: str,
    decision: str,
) -> None:
    now = datetime.now(UTC)
    viewer, authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    ref = authority.session_ref(browser, allowance.allowance_id)
    assert isinstance(ref, ConsoleSessionRef)
    if decision in {"renewal", "open", "active"}:
        assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream: ConsoleEventStream | None = None
    if decision == "active":
        opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
        assert isinstance(opened, ConsoleEventStream)
        assert b"event: chunk" in next(opened.events)
        stream = opened

    _change_target(tenant, ref, target_change)

    if decision == "discovery":
        assert viewer.visible_sessions(browser) == ()
    elif decision == "mint":
        refusal = viewer.mint_grant(browser, allowance.allowance_id)
        assert isinstance(refusal, RecordProblem)
        assert refusal.code == "console-session-join-stale"
    elif decision == "renewal":
        refusal = viewer.mint_grant(browser, allowance.allowance_id, renewal=True)
        assert isinstance(refusal, RecordProblem)
        assert refusal.code == "console-session-join-stale"
    elif decision == "open":
        open_refusal = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
        assert isinstance(open_refusal, RecordProblem)
        assert open_refusal.code == "console-session-revoked"
    else:
        assert stream is not None
        closed = next(stream.events)
        assert b'"code":"revoked"' in closed
        _assert_event_schema(closed)


def _change_target(tenant: TenantFixture, ref: ConsoleSessionRef, target_change: str) -> None:
    statement = (
        "UPDATE principals SET disabled = true WHERE principal_id = %s"
        if target_change == "disabled"
        else "UPDATE principals SET kind = 'commander' WHERE principal_id = %s"
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(statement, (ref.seat_principal_id,))


def test_default_pending_cap_closes_a_backpressured_asgi_stream_within_five_seconds(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    adapter.payload = b"x" * (17 * 16 * 1024)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)

    messages, elapsed = asyncio.run(_hold_first_asgi_send(tenant, stream))
    bodies = [cast(bytes, message.get("body", b"")) for message in messages]
    gap = next(body for body in bodies if b"event: gap" in body)
    closed = next(body for body in bodies if b"event: closed" in body)

    assert b'"reason":"slow_consumer"' in gap
    assert b'"code":"slow_consumer"' in closed
    assert elapsed <= _MAX_CLOSE_SECONDS
    _assert_event_schema(gap)
    _assert_event_schema(closed)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            "SELECT reason FROM console_output_gap_facts WHERE allowance_id = %s",
            (allowance.allowance_id,),
        ).fetchall()
    assert facts == [{"reason": "slow_consumer"}]


def test_first_subcap_frame_transport_stall_commits_slow_consumer_gap_and_close(
    tenant: TenantFixture,
) -> None:
    ref = recorded_session_ref(tenant)
    adapter = Adapter(observation(ref), b"one-frame")
    authority = PostgresConsoleAuthority(
        tenant.database.runtime_dsn,
        policy=replace(policy(), revocation_poll_seconds=1),
    )
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"first-frame-stall").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=datetime.now(UTC))
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)

    elapsed = asyncio.run(_stall_first_subcap_frame(stream))

    assert elapsed <= _MAX_CLOSE_SECONDS
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT gap.reason, close.code, close.gap_required
            FROM console_output_gap_facts AS gap
            CROSS JOIN console_stream_closes AS close
            WHERE gap.allowance_id = %s AND close.stream_id = %s
            """,
            (allowance.allowance_id, stream.lease.stream_id),
        ).fetchone()
    assert facts == {
        "reason": "slow_consumer",
        "code": "slow_consumer",
        "gap_required": True,
    }


async def _stall_first_subcap_frame(stream: ConsoleEventStream) -> float:
    response = console_streaming_response(stream)
    first_body = asyncio.Event()
    never_release = asyncio.Event()

    async def send(message: dict[str, object]) -> None:
        if message.get("type") == "http.response.body" and message.get("body"):
            first_body.set()
            await never_release.wait()

    task = asyncio.create_task(response.stream_response(cast(Send, send)))
    await asyncio.wait_for(first_body.wait(), timeout=2)
    started = time.monotonic()
    with pytest.raises(OSError, match="bounded send deadline"):
        await asyncio.wait_for(task, timeout=_MAX_CLOSE_SECONDS)
    return time.monotonic() - started


async def _hold_first_asgi_send(
    tenant: TenantFixture, stream: ConsoleEventStream
) -> tuple[list[dict[str, object]], float]:
    response = console_streaming_response(stream)
    release = asyncio.Event()
    first_body = asyncio.Event()
    messages: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        messages.append(message)
        if (
            message.get("type") == "http.response.body"
            and message.get("body")
            and not first_body.is_set()
        ):
            first_body.set()
            await release.wait()

    task = asyncio.create_task(response.stream_response(cast(Send, send)))
    await asyncio.wait_for(first_body.wait(), timeout=2)
    started = time.monotonic()
    close_code: str | None = None
    while time.monotonic() - started <= _MAX_CLOSE_SECONDS:
        close_code = await asyncio.to_thread(_stream_close_code, tenant, stream)
        if close_code is not None:
            break
        await asyncio.sleep(0.01)
    elapsed = time.monotonic() - started
    release.set()
    await asyncio.wait_for(task, timeout=2)
    assert close_code == "slow_consumer"
    return messages, elapsed


def _stream_close_code(tenant: TenantFixture, stream: ConsoleEventStream) -> str | None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT code FROM console_stream_closes WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
    return None if row is None else str(row[0])


def _assert_event_schema(event: bytes) -> None:
    validator = Draft202012Validator(
        json.loads(
            (
                Path(__file__).parents[3]
                / "contracts/domain/console/console-stream-event.schema.json"
            ).read_text(encoding="utf-8")
        )
    )
    data = next(
        line.removeprefix(b"data: ") for line in event.splitlines() if line.startswith(b"data: ")
    )
    validator.validate(json.loads(data))


def test_delivery_overflow_commits_gap_before_typed_close_without_extra_output(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    authority.policy = replace(authority.policy, delivery_window_bytes=16 * 1024)
    adapter.payload = b"a" * (16 * 1024) + b"b"
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)

    chunk = next(stream.events)
    gap = next(stream.events)
    closed = next(stream.events)

    assert b"event: chunk" in chunk
    assert b'"reason":"rate_limited"' in gap
    assert b'"code":"rate_limited"' in closed
    _assert_event_schema(chunk)
    _assert_event_schema(gap)
    _assert_event_schema(closed)
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_output_objects
                 WHERE allowance_id = %s) AS outputs,
                (SELECT count(*) FROM console_output_access_facts
                 WHERE stream_id = %s) AS accesses,
                (SELECT count(*) FROM console_output_recovery_facts AS recovery
                 JOIN console_output_access_facts AS access USING (access_id)
                 WHERE access.stream_id = %s) AS recoveries,
                (SELECT min(cursor) FROM console_output_gap_facts
                 WHERE allowance_id = %s AND reason = 'rate_limited') AS gap_cursor,
                (SELECT max(cursor) FROM console_output_objects
                 WHERE allowance_id = %s) AS output_cursor,
                (SELECT code FROM console_stream_closes
                 WHERE stream_id = %s) AS close_code
            """,
            (
                allowance.allowance_id,
                stream.lease.stream_id,
                stream.lease.stream_id,
                allowance.allowance_id,
                allowance.allowance_id,
                stream.lease.stream_id,
            ),
        ).fetchone()
    assert facts is not None
    assert facts["outputs"] == 1
    assert facts["accesses"] == 1
    assert facts["recoveries"] == 1
    assert cast(int, facts["output_cursor"]) < cast(int, facts["gap_cursor"])
    assert facts["close_code"] == "rate_limited"


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [
        ("global", "globally_disabled"),
        ("session", "revoked"),
        ("human-session", "reauthentication_required"),
        ("human-binding", "reauthentication_required"),
        ("assignment", "revoked"),
        ("work-session", "revoked"),
        ("policy", "fenced"),
    ],
)
def test_active_stream_rechecks_every_mutable_authority_within_the_poll_bound(
    tenant: TenantFixture,
    change: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    viewer, authority, _adapter, operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    assert b"event: chunk" in next(stream.events)

    apply_first_open_change(
        change,
        tenant,
        viewer,
        authority,
        operator,
        browser,
        allowance,
        now=now,
    )
    closed = next(stream.events)
    assert f'"code":"{expected_code}"'.encode() in closed
    _assert_event_schema(closed)
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT code, closed_at FROM console_stream_closes WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
    assert row == {"code": expected_code, "closed_at": now}
    assert cast(datetime, row["closed_at"]) <= now + timedelta(seconds=5)


def test_envelope_authentication_failure_emits_a_durable_gap_and_typed_close(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)

    def invalid_envelope(*_args: object, **_kwargs: object) -> bytes:
        raise ValueError("injected envelope authentication failure")

    monkeypatch.setattr(AesGcmConsoleCipher, "decrypt", invalid_envelope)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert not isinstance(stream, RecordProblem)
    gap = next(stream.events)
    closed = next(stream.events)

    assert b'"reason":"cursor_unavailable"' in gap
    assert b'"code":"output_unavailable"' in closed
    _assert_event_schema(gap)
    _assert_event_schema(closed)
    with pytest.raises(StopIteration):
        next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT gap.reason, close.code
            FROM console_output_gap_facts AS gap
            CROSS JOIN console_stream_closes AS close
            WHERE close.stream_id = %s
            """,
            (stream.lease.stream_id,),
        ).fetchone()
    assert facts == {"reason": "cursor_unavailable", "code": "output_unavailable"}


def test_unprovable_reconnect_cursor_emits_one_durable_gap_then_resumes(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=999_999)
    assert isinstance(stream, ConsoleEventStream)

    gap = next(stream.events)
    chunk = next(stream.events)

    assert gap.count(b"event: gap") == 1
    assert b'"reason":"unprovable_range"' in gap
    assert gap.startswith(b"id: ")
    _assert_event_schema(gap)
    _assert_event_schema(chunk)
    assert b"event: chunk" in chunk
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        gaps = connection.execute(
            """
            SELECT cursor, reason FROM console_output_gap_facts
            WHERE allowance_id = %s ORDER BY cursor
            """,
            (allowance.allowance_id,),
        ).fetchall()
    gap_cursor = int(gap.splitlines()[0].removeprefix(b"id: "))
    assert gaps == [{"cursor": gap_cursor, "reason": "unprovable_range"}]
    assert int(chunk.splitlines()[0].removeprefix(b"id: ")) > gap_cursor
    cast(Generator[bytes, None, None], stream.events).close()


def test_revocation_between_replay_items_prevents_the_next_content_access(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, operator, browser, allowance = console_setup(tenant, now)
    adapter.payload = b"a" * (16 * 1024) + b"b" * (16 * 1024)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    original = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(original, ConsoleEventStream)
    assert b"event: chunk" in next(original.events)
    assert b"event: chunk" in next(original.events)
    cast(Generator[bytes, None, None], original.events).close()
    assert isinstance(
        viewer.mint_grant(browser, allowance.allowance_id, renewal=True), ConsoleViewGrant
    )
    replay = viewer.open_stream(browser, allowance.allowance_id, last_event_id=0)
    assert isinstance(replay, ConsoleEventStream)
    assert b"event: chunk" in next(replay.events)

    assert (
        viewer.revoke_session(
            operator,
            ConsoleSessionRevocation(allowance.allowance_id, "replay revocation proof"),
        )
        is None
    )
    closed = next(replay.events)
    assert b'"code":"revoked"' in closed
    _assert_event_schema(closed)
    with pytest.raises(StopIteration):
        next(replay.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        replay_accesses = connection.execute(
            """
            SELECT count(*) AS count FROM console_output_access_facts
            WHERE stream_id = %s AND access_kind = 'reconnect'
            """,
            (replay.lease.stream_id,),
        ).fetchone()
    assert replay_accesses == {"count": 1}


def test_committed_reader_access_id_can_recover_content_only_once(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)
    assert b"event: chunk" in next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        access = connection.execute("SELECT access_id FROM console_output_access_facts").fetchone()
        recovery = connection.execute(
            "SELECT count(*) AS count FROM console_output_recovery_facts"
        ).fetchone()
    assert access is not None and recovery == {"count": 1}
    with (
        pytest.raises(psycopg.errors.UniqueViolation),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            "SELECT * FROM recover_console_output_object(%s, %s)",
            (access["access_id"], now),
        ).fetchall()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM console_output_recovery_facts").fetchone()
    assert count == (1,)
    cast(Generator[bytes, None, None], stream.events).close()
