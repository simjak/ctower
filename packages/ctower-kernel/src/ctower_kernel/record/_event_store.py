"""Postgres persistence for typed canonical Record event envelopes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_kernel.record.events import EventEnvelope, event_digest
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

type EventSubject = tuple[str, UUID]


def append_event(
    connection: psycopg.Connection[dict[str, object]],
    event: EventEnvelope,
    *,
    subjects: tuple[EventSubject, ...] = (),
) -> None:
    position_row = connection.execute(
        """
        UPDATE record_position_ledger SET last_position = last_position + 1
        WHERE singleton RETURNING last_position
        """
    ).fetchone()
    if position_row is None:
        raise RuntimeError("record position ledger is unavailable")
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash, record_position
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            event.event_id,
            event.tenant_id,
            event.stream_id,
            event.aggregate_id,
            event.sequence,
            event.kind.value,
            event.schema_version,
            event.actor_principal_id,
            event.client_command_id,
            event.request_sha256,
            event.correlation_id,
            event.causation_id,
            event.origin.value,
            event.server_time,
            Jsonb(event.payload.to_mapping()),
            event.prev_hash,
            event_digest(event),
            position_row["last_position"],
        ),
    )
    if subjects:
        connection.cursor().executemany(
            """
            INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
            VALUES (%s, %s, %s, %s)
            """,
            (
                (event.event_id, event.tenant_id, subject_kind, subject_id)
                for subject_kind, subject_id in subjects
            ),
        )


def enqueue_event(
    connection: psycopg.Connection[dict[str, object]],
    outbox_id: UUID,
    event: EventEnvelope,
    telemetry: TelemetryContext,
    now: datetime,
    *,
    topic: str = "record.events",
) -> None:
    connection.execute(
        """
        INSERT INTO outbox (
            outbox_id, tenant_id, event_id, topic, payload, telemetry, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            outbox_id,
            event.tenant_id,
            event.event_id,
            topic,
            Jsonb(event.to_mapping()),
            Jsonb(telemetry.to_mapping()),
            now,
        ),
    )
