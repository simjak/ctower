"""Canonical inbound and Request events for one manifest-bound import."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid5

from ctower_kernel.record import Actor
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    InboundEventRecordedPayload,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.request_events import RequestChangedPayload
from ctower_kernel.record.transaction import EventCommit
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_common_sql import CUTOVER_NAMESPACE
from ctower_kernel.work._request_cutover_types import RequestCutoverImport, RequestCutoverResult

__all__ = ["import_events", "import_identities"]

_ZERO_HASH = bytes(32)


def import_events(
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    result: RequestCutoverResult,
    *,
    identities: tuple[UUID, UUID, UUID],
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventCommit, ...]:
    del result
    thread_id, inbound_event_id, request_id = identities
    inbound = _inbound_event(
        actor,
        command,
        row,
        thread_id,
        inbound_event_id,
        request_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    request = _request_event(
        actor,
        command,
        row,
        inbound_event_id,
        request_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    return (EventCommit(inbound, uuid7(now)), EventCommit(request, uuid7(now)))


def _inbound_event(
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    thread_id: UUID,
    inbound_event_id: UUID,
    request_id: UUID,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid7(now),
        kind=EventKind.INBOUND_EVENT_RECORDED,
        origin=EventOrigin.API,
        payload=InboundEventRecordedPayload(
            inbound_event_id,
            "mission-control-request",
            command.source_request_id,
            cast(str, row["project_key"]),
            1,
            "create_request",
            "authenticated",
            "request_created",
            cast(str, row["content_sha256"]),
            None,
            request_id,
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"inbound-thread:{thread_id}",
        tenant_id=actor.tenant_id,
    )


def _request_event(
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    inbound_event_id: UUID,
    request_id: UUID,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    projection = cast(dict[str, object], row["projection"])
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=request_id,
        causation_id=inbound_event_id,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid7(now),
        kind=EventKind.REQUEST_CHANGED,
        origin=EventOrigin.API,
        payload=RequestChangedPayload(
            "import",
            request_id,
            cast(int, row["request_number"]),
            cast(str, row["project_key"]),
            1,
            command.content,
            cast(str, row["content_sha256"]),
            "mission-control-request",
            command.source_request_id,
            actor.principal_id,
            UUID(cast(str, row["mapped_principal_id"])),
            cast(str, projection["triage"]),
            cast(str, projection["priority"]),
            row["source_status"] == "NEW",
            (),
            (),
            ("source_blocked",) if bool(projection["blocker"]) else (),
            "open",
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"request:{request_id}",
        tenant_id=actor.tenant_id,
    )


def import_identities(ledger_digest: str, source_request_id: str) -> tuple[UUID, UUID, UUID]:
    base = f"{ledger_digest}:{source_request_id}"
    thread_id, inbound_event_id, request_id = (
        uuid5(CUTOVER_NAMESPACE, f"{base}:{kind}")
        for kind in ("thread", "inbound-event", "request")
    )
    return thread_id, inbound_event_id, request_id
