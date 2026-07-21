"""Lower Record Interface for canonical command and event commits."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_kernel.record import RecordProblem
from ctower_kernel.record._commands import reserve_command
from ctower_kernel.record._event_store import EventSubject, append_event, enqueue_event
from ctower_kernel.record.events import EventEnvelope
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["RecordTransaction"]


class RecordTransaction:
    """Keep idempotency ordering and canonical append choreography Record-owned."""

    def __init__(self, connection: psycopg.Connection[dict[str, object]]) -> None:
        self._connection = connection

    def reserve(
        self,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
    ) -> dict[str, object] | RecordProblem | None:
        """Reserve a principal command key before any aggregate read."""

        return reserve_command(self._connection, principal_id, command_id, request_digest)

    def commit(
        self,
        event: EventEnvelope,
        *,
        outbox_id: UUID,
        response_body: dict[str, object],
        status_code: int,
        telemetry: TelemetryContext,
        now: datetime,
        subjects: tuple[EventSubject, ...] = (),
    ) -> None:
        """Append one event, exact result, and outbox row in the caller's transaction."""

        append_event(self._connection, event, subjects=subjects)
        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.tenant_id,
                event.actor_principal_id,
                event.client_command_id,
                event.request_sha256,
                status_code,
                Jsonb(response_body),
                [event.event_id],
                now,
            ),
        )
        enqueue_event(self._connection, outbox_id, event, telemetry, now)

    def refuse(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        problem: RecordProblem,
        *,
        now: datetime,
    ) -> None:
        """Persist one exact typed refusal without an event or authoritative mutation."""

        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                principal_id,
                command_id,
                request_digest,
                problem.status,
                Jsonb(problem.response_payload()),
                [],
                now,
            ),
        )
