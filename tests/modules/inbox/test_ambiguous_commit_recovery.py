"""Focused ambiguous-commit/replay coverage for native-inbox durable writes.

B336-1: both PostgresInbox commands must route their SQL mutation through the
established recover_ambiguous_commit envelope, exactly like the sibling durable
authority-write adapters. If PostgreSQL commits but the connection dies while
returning, the durable event can exist while the API raises -- the ambiguous-commit
boundary is broken. These tests patch the SQL layer to fail once at the commit
boundary, then prove the adapter replays and still returns the durable result.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

import ctower_kernel.inbox.postgres as inbox_postgres
from ctower_kernel.inbox import (
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
    PostgresInbox,
)
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_DSN = "postgresql://unused"
_REPLAY_ATTEMPTS = 2


def _actor() -> Actor:
    return Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)


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


def _send_result() -> InboxSendResult:
    now = datetime.now(UTC)
    return InboxSendResult(
        command_id=uuid4(),
        event_ids=(uuid4(), uuid4()),
        from_seat="ctower-commander",
        message_id=uuid4(),
        position=1,
        sent_at=now,
        thread_id=uuid4(),
        thread_version=2,
        to="qa-agent",
    )


def _promotion_result() -> InboxPromotionResult:
    return InboxPromotionResult(
        command_id=uuid4(),
        event_id=uuid4(),
        thread_id=uuid4(),
        thread_version=3,
        ticket_id=uuid4(),
    )


def test_send_replays_through_recover_ambiguous_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable = _send_result()
    calls = 0

    def flaky_send_message(*_args: object, **_kwargs: object) -> InboxSendResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise psycopg.errors.QueryCanceled("connection lost after COMMIT was sent")
        return durable

    monkeypatch.setattr(inbox_postgres, "send_message", flaky_send_message)
    inbox = PostgresInbox(_DSN)

    outcome = inbox.send(
        _actor(),
        InboxSendCommand(uuid4(), "qa-agent", "durable replay"),
        request_digest=bytes(32),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert outcome is durable
    assert calls == _REPLAY_ATTEMPTS


def test_promote_replays_through_recover_ambiguous_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable = _promotion_result()
    calls = 0

    def flaky_promote_thread(*_args: object, **_kwargs: object) -> InboxPromotionResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise psycopg.OperationalError("connection lost after COMMIT was sent")
        return durable

    monkeypatch.setattr(inbox_postgres, "promote_thread", flaky_promote_thread)
    inbox = PostgresInbox(_DSN)

    outcome = inbox.promote(
        _actor(),
        InboxPromotionCommand(uuid4(), 2, uuid4(), uuid4()),
        request_digest=bytes(32),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert outcome is durable
    assert calls == _REPLAY_ATTEMPTS
