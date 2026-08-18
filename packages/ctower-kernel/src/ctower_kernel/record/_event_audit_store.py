"""Postgres adapter for canonical event cursor reads."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ctower_kernel.record._audit_sql import ticket_audit as _ticket_audit
from ctower_kernel.record._movement_event_sql import movement_counts as _movement_counts
from ctower_kernel.record._movement_event_sql import movement_events as _movement_events
from ctower_kernel.record._project_event_sql import project_events as _project_events
from ctower_kernel.record.interface import Actor, AuditPage, RecordProblem
from ctower_kernel.record.movement_events import MovementCountList, MovementEventPage
from ctower_kernel.record.project_events import ProjectEventPage
from ctower_kernel.telemetry import Telemetry, TelemetryContext


class _PostgresEventAudit:
    """Postgres adapter for the cohesive canonical-event cursor-read boundary."""

    def __init__(self, dsn: str, *, telemetry: Telemetry) -> None:
        self._dsn = dsn
        self._telemetry = telemetry

    def ticket_audit(
        self,
        actor: Actor,
        ticket_id: UUID,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> AuditPage | RecordProblem:
        outcome = _ticket_audit(
            self._dsn, actor, ticket_id, project_key, cursor=cursor, limit=limit
        )
        self._emit("record.ticket_audit", telemetry, outcome)
        return outcome

    def project_events(
        self,
        actor: Actor,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> ProjectEventPage | RecordProblem:
        outcome = _project_events(self._dsn, actor, project_key, cursor=cursor, limit=limit)
        self._emit("record.project_events", telemetry, outcome)
        return outcome

    def movement_events(
        self,
        actor: Actor,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> MovementEventPage | RecordProblem:
        outcome = _movement_events(self._dsn, actor, project_key, cursor=cursor, limit=limit)
        self._emit("record.movement_events", telemetry, outcome)
        return outcome

    def movement_counts(
        self,
        actor: Actor,
        *,
        telemetry: TelemetryContext,
    ) -> MovementCountList | RecordProblem:
        outcome = _movement_counts(self._dsn, actor, now=datetime.now(UTC))
        self._emit("record.movement_counts", telemetry, outcome)
        return outcome

    def _emit(self, name: str, telemetry: TelemetryContext, outcome: object) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
