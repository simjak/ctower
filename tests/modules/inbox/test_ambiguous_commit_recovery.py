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
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxAcknowledgeResult,
    InboxPromotionCommand,
    InboxPromotionOutcome,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
    PostgresInbox,
)
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.events import EventOrigin
from ctower_kernel.record.inbox_events import InboxParticipant
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
        event_ids=(uuid4(),),
        outcome=InboxPromotionOutcome.TICKET_LINKED,
        thread_id=uuid4(),
        thread_version=3,
        ticket_id=uuid4(),
    )


def _acknowledge_result() -> InboxAcknowledgeResult:
    now = datetime.now(UTC)
    return InboxAcknowledgeResult(
        command_id=uuid4(),
        delivered_at=now,
        event_ids=(uuid4(), uuid4()),
        message_id=uuid4(),
        read_at=now,
        state=InboxAcknowledgementState.READ,
        thread_id=uuid4(),
        thread_version=4,
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


def test_notification_replays_through_recover_ambiguous_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable = _send_result()
    calls = 0

    def flaky_ingest_notification(*_args: object, **_kwargs: object) -> InboxSendResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise psycopg.errors.QueryCanceled("connection lost after COMMIT was sent")
        return durable

    monkeypatch.setattr(inbox_postgres, "ingest_notification", flaky_ingest_notification)
    inbox = PostgresInbox(_DSN)

    outcome = inbox.ingest_notification(
        _actor(),
        InboxSendCommand(uuid4(), "qa-agent", "durable notification replay"),
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
        InboxPromotionCommand(uuid4(), uuid4(), uuid4()),
        request_digest=bytes(32),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert outcome is durable
    assert calls == _REPLAY_ATTEMPTS


def test_acknowledge_replays_through_recover_ambiguous_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable = _acknowledge_result()
    calls = 0

    def flaky_acknowledge_message(*_args: object, **_kwargs: object) -> InboxAcknowledgeResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise psycopg.OperationalError("connection lost after COMMIT was sent")
        return durable

    monkeypatch.setattr(inbox_postgres, "acknowledge_message", flaky_acknowledge_message)
    inbox = PostgresInbox(_DSN)

    outcome = inbox.acknowledge(
        _actor(),
        InboxAcknowledgeCommand(uuid4(), uuid4(), InboxAcknowledgementState.READ),
        request_digest=bytes(32),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert outcome is durable
    assert calls == _REPLAY_ATTEMPTS


def test_import_send_command_preserves_source_identity_and_original_timestamp() -> None:
    sent_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    message_id = uuid4()
    command = InboxSendCommand(
        uuid4(),
        "operator",
        "Subject\n\nbody",
        message_id=message_id,
        sent_at=sent_at,
        source_ref="inbox.jsonl#17",
        source_sender="unknown-mc-seat",
        source_recipient="operator",
        origin=EventOrigin.MIGRATION_IMPORTER,
    )

    assert command.message_id == message_id
    assert command.sent_at == sent_at
    assert command.source_ref == "inbox.jsonl#17"
    assert command.source_sender == "unknown-mc-seat"
    assert command.source_recipient == "operator"
    assert command.origin is EventOrigin.MIGRATION_IMPORTER


def test_import_message_commit_uses_supplied_identity_and_timestamp() -> None:
    sent_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    message_id = uuid4()
    actor = _actor()
    sender = InboxParticipant(uuid4(), "source-sender")
    recipient = InboxParticipant(uuid4(), "operator")
    command = InboxSendCommand(
        uuid4(),
        recipient.seat_key,
        "imported body",
        message_id=message_id,
        sent_at=sent_at,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )

    result, commits, _ = inbox_postgres.message_commits(
        actor,
        command,
        sender,
        recipient,
        None,
        thread_id=uuid4(),
        request_digest=bytes(32),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert result.message_id == message_id
    assert result.sent_at == sent_at
    assert all(item.event.origin is EventOrigin.MIGRATION_IMPORTER for item in commits)


def test_import_acknowledge_command_carries_source_recorded_at() -> None:
    recorded_at = datetime(2026, 8, 14, 20, 30, tzinfo=UTC)
    command = InboxAcknowledgeCommand(
        uuid4(),
        uuid4(),
        InboxAcknowledgementState.READ,
        recorded_at=recorded_at,
        origin=EventOrigin.MIGRATION_IMPORTER,
    )

    assert command.recorded_at == recorded_at
    assert command.origin is EventOrigin.MIGRATION_IMPORTER
