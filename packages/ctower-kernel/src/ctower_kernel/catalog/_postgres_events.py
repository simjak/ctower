"""Canonical Catalog event chain construction for one atomic apply."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg

from ctower_kernel.catalog._postgres_revisions import RevisionState
from ctower_kernel.catalog.interface import CompanyBundleApply, ComponentReference
from ctower_kernel.record import Actor
from ctower_kernel.record.catalog_events import (
    CatalogBundleActivatedPayload,
    CatalogComponentPublishedPayload,
    CatalogComponentReference,
)
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, event_digest
from ctower_kernel.record.transaction import EventCommit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class _EventCursor:
    sequence: int
    event_id: UUID | None
    event_hash: bytes


def catalog_events(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CompanyBundleApply,
    states: tuple[RevisionState, ...],
    *,
    active_version: int,
    bundle_digest: str,
    plan_digest: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[tuple[RevisionState, ...], tuple[EventCommit, ...]]:
    cursor = _event_cursor(connection, actor.tenant_id)
    commits: list[EventCommit] = []
    updated: list[RevisionState] = []
    for state in states:
        if not state.is_new:
            updated.append(state)
            continue
        event = _event(
            actor,
            command,
            cursor,
            EventKind.CATALOG_COMPONENT_PUBLISHED,
            CatalogComponentPublishedPayload(
                component=_event_reference(state.resource.component.reference()),
                object_version=state.receipt.receipt.object_version,
                payload_ref=state.resource.component.payload_ref,
            ),
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        commits.append(EventCommit(event=event, outbox_id=uuid4()))
        cursor = _next_cursor(event)
        updated.append(replace(state, publication_event_id=event.event_id))
    member_event_ids = tuple(cast(UUID, state.publication_event_id) for state in updated)
    bundle_event = _event(
        actor,
        command,
        cursor,
        EventKind.CATALOG_BUNDLE_ACTIVATED,
        CatalogBundleActivatedPayload(
            active_version=active_version,
            bundle_digest=bundle_digest,
            member_event_ids=member_event_ids,
            plan_digest=plan_digest,
        ),
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    commits.append(EventCommit(event=bundle_event, outbox_id=uuid4()))
    return tuple(updated), tuple(commits)


def _event(
    actor: Actor,
    command: CompanyBundleApply,
    cursor: _EventCursor,
    kind: EventKind,
    payload: CatalogComponentPublishedPayload | CatalogBundleActivatedPayload,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=actor.tenant_id,
        causation_id=cursor.event_id,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid4(),
        kind=kind,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=cursor.event_hash,
        request_sha256=request_digest,
        sequence=cursor.sequence + 1,
        server_time=now,
        stream_id=f"catalog:{actor.tenant_id}",
        tenant_id=actor.tenant_id,
    )


def _event_cursor(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> _EventCursor:
    row = connection.execute(
        """
        SELECT event_id, event_hash, sequence
        FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, f"catalog:{tenant_id}"),
    ).fetchone()
    if row is None:
        return _EventCursor(0, None, _ZERO_HASH)
    return _EventCursor(
        int(cast(int, row["sequence"])),
        cast(UUID, row["event_id"]),
        bytes(cast(bytes, row["event_hash"])),
    )


def _next_cursor(event: EventEnvelope) -> _EventCursor:
    return _EventCursor(event.sequence, event.event_id, event_digest(event))


def _event_reference(reference: ComponentReference) -> CatalogComponentReference:
    return CatalogComponentReference(
        content_digest=reference.content_digest,
        key=reference.key,
        kind=reference.kind.value,
        revision=reference.revision,
    )
