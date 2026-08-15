"""Typed knowledge-base event construction."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.knowledge.models import KnowledgeAddCommand
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventEnvelope, EventKind
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.knowledge_events import KnowledgeDocumentRegisteredPayload
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def _document_registered_event(
    actor: Actor,
    command: KnowledgeAddCommand,
    document_id: UUID,
    request_digest: bytes,
    recorded_at: datetime,
    now: datetime,
    telemetry: TelemetryContext,
    *,
    body: str,
    title: str,
) -> EventEnvelope:
    event_id = uuid7(now)
    registered_at = recorded_at
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=document_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.KNOWLEDGE_DOCUMENT_REGISTERED,
        origin=command.origin,
        payload=KnowledgeDocumentRegisteredPayload(
            body=body,
            document_id=document_id,
            registered_by=actor.principal_id,
            registered_at=registered_at,
            scope=command.scope,
            title=title,
            project_key=command.project_key,
            source_ref=command.source_ref,
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"knowledge-document:{document_id}",
        tenant_id=actor.tenant_id,
    )
