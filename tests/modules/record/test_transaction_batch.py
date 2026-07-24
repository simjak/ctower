from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
import pytest

import ctower_kernel.record.transaction as transaction_module
from ctower_kernel.record.events import (
    CatalogBundleActivatedPayload,
    CatalogComponentPublishedPayload,
    CatalogComponentReference,
    EventEnvelope,
    EventKind,
    EventOrigin,
    event_digest,
)
from ctower_kernel.record.transaction import EventCommit, RecordTransaction
from ctower_kernel.telemetry import TelemetryContext

_ACTOR_ID = UUID("00000000-0000-4000-8000-000000000001")
_COMMAND_ID = UUID("00000000-0000-4000-8000-000000000002")
_COMPONENT_EVENT_ID = UUID("00000000-0000-4000-8000-000000000003")
_BUNDLE_EVENT_ID = UUID("00000000-0000-4000-8000-000000000004")
_TENANT_ID = UUID("00000000-0000-4000-8000-000000000005")
_NOW = datetime(2026, 7, 24, tzinfo=UTC)
_DIGEST = "sha256:" + "1" * 64
_PLAN_DIGEST = "sha256:" + "2" * 64


class _Result:
    def fetchone(self) -> dict[str, object] | None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> _Result:
        self.calls.append((query, params))
        return _Result()


def test_batch_commit_appends_all_events_and_one_exact_command_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    appended: list[EventEnvelope] = []
    enqueued: list[tuple[UUID, EventEnvelope, str]] = []
    first, second = _catalog_events()

    def append(
        connection_value: object,
        event: EventEnvelope,
        *,
        subjects: tuple[tuple[str, UUID], ...],
    ) -> None:
        del connection_value
        assert subjects == ()
        appended.append(event)

    def enqueue(
        connection_value: object,
        outbox_id: UUID,
        event: EventEnvelope,
        telemetry: TelemetryContext,
        now: datetime,
        *,
        topic: str,
    ) -> None:
        del connection_value, telemetry
        assert now == _NOW
        enqueued.append((outbox_id, event, topic))

    monkeypatch.setattr(transaction_module, "append_event", append)
    monkeypatch.setattr(transaction_module, "enqueue_event", enqueue)
    commits = (
        EventCommit(first, UUID("00000000-0000-4000-8000-000000000006")),
        EventCommit(second, UUID("00000000-0000-4000-8000-000000000007")),
    )

    RecordTransaction(_as_connection(connection)).commit_batch(
        commits,
        response_body={"active_version": 1},
        status_code=200,
        telemetry=_telemetry(),
        now=_NOW,
    )

    assert appended == [first, second]
    assert [(item[0], item[1].event_id, item[2]) for item in enqueued] == [
        (commits[0].outbox_id, first.event_id, "record.events"),
        (commits[1].outbox_id, second.event_id, "record.events"),
    ]
    assert len(connection.calls) == 1
    assert "INSERT INTO command_results" in connection.calls[0][0]
    assert connection.calls[0][1][6] == [first.event_id, second.event_id]


def test_batch_commit_refuses_empty_or_mixed_commands_before_writes() -> None:
    connection = _Connection()
    transaction = RecordTransaction(_as_connection(connection))
    first, second = _catalog_events()
    different_command = replace(
        second,
        client_command_id=UUID("00000000-0000-4000-8000-000000000099"),
    )

    with pytest.raises(ValueError, match="must not be empty"):
        transaction.commit_batch(
            (),
            response_body={},
            status_code=200,
            telemetry=_telemetry(),
            now=_NOW,
        )
    with pytest.raises(ValueError, match="one exact command"):
        transaction.commit_batch(
            (
                EventCommit(first, UUID("00000000-0000-4000-8000-000000000006")),
                EventCommit(
                    different_command,
                    UUID("00000000-0000-4000-8000-000000000007"),
                ),
            ),
            response_body={},
            status_code=200,
            telemetry=_telemetry(),
            now=_NOW,
        )

    assert connection.calls == []


def _catalog_events() -> tuple[EventEnvelope, EventEnvelope]:
    component = EventEnvelope(
        actor_principal_id=_ACTOR_ID,
        aggregate_id=_TENANT_ID,
        causation_id=None,
        client_command_id=_COMMAND_ID,
        correlation_id=_COMMAND_ID,
        event_id=_COMPONENT_EVENT_ID,
        kind=EventKind.CATALOG_COMPONENT_PUBLISHED,
        origin=EventOrigin.API,
        payload=CatalogComponentPublishedPayload(
            component=CatalogComponentReference(
                content_digest=_DIGEST,
                key="example.component",
                kind="workflow",
                revision=1,
            ),
            object_version="version-1",
            payload_ref="object:" + _DIGEST,
        ),
        prev_hash=bytes(32),
        request_sha256=bytes.fromhex("3" * 64),
        sequence=1,
        server_time=_NOW,
        stream_id=f"catalog:{_TENANT_ID}",
        tenant_id=_TENANT_ID,
    )
    bundle = EventEnvelope(
        actor_principal_id=_ACTOR_ID,
        aggregate_id=_TENANT_ID,
        causation_id=component.event_id,
        client_command_id=_COMMAND_ID,
        correlation_id=_COMMAND_ID,
        event_id=_BUNDLE_EVENT_ID,
        kind=EventKind.CATALOG_BUNDLE_ACTIVATED,
        origin=EventOrigin.API,
        payload=CatalogBundleActivatedPayload(
            active_version=1,
            bundle_digest=_DIGEST,
            member_event_ids=(component.event_id,),
            plan_digest=_PLAN_DIGEST,
        ),
        prev_hash=event_digest(component),
        request_sha256=component.request_sha256,
        sequence=2,
        server_time=_NOW,
        stream_id=f"catalog:{_TENANT_ID}",
        tenant_id=_TENANT_ID,
    )
    return component, bundle


def _telemetry() -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(_COMMAND_ID),
        causation_id=str(_COMMAND_ID),
        tenant_id=str(_TENANT_ID),
        actor_id=str(_ACTOR_ID),
        command_id=str(_COMMAND_ID),
    )


def _as_connection(
    connection: _Connection,
) -> psycopg.Connection[dict[str, object]]:
    return cast(psycopg.Connection[dict[str, object]], connection)
