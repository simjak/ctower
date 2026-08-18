"""Postgres adapter for the cohesive ticket read boundary."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.record._ticket_sql import get_ticket as _get_ticket
from ctower_kernel.record._ticket_sql import resolve_display_key as _resolve_display_key
from ctower_kernel.record._ticket_sql import ticket_timeline as _ticket_timeline
from ctower_kernel.record.interface import Actor, RecordProblem, Ticket, TicketTimeline
from ctower_kernel.telemetry import Telemetry, TelemetryContext

__all__ = ["PostgresTickets"]


class PostgresTickets:
    """Postgres adapter serving UUID and display-key ticket references alike."""

    def __init__(self, dsn: str, *, telemetry: Telemetry) -> None:
        self._dsn = dsn
        self._telemetry = telemetry

    def get(
        self,
        actor: Actor,
        reference: UUID | str,
        project_key: str,
        *,
        telemetry: TelemetryContext,
    ) -> Ticket | RecordProblem:
        """Read one tenant/project-scoped ticket."""

        outcome = _get_ticket(self._dsn, actor, reference, project_key, telemetry=telemetry)
        self._emit("record.get_ticket", telemetry, outcome)
        return outcome

    def timeline(
        self,
        actor: Actor,
        reference: UUID | str,
        project_key: str,
        *,
        telemetry: TelemetryContext,
    ) -> TicketTimeline | RecordProblem:
        """Read one tenant/project-scoped event timeline."""

        outcome = _ticket_timeline(self._dsn, actor, reference, project_key, telemetry=telemetry)
        self._emit("record.ticket_timeline", telemetry, outcome)
        return outcome

    def resolve_display_key(
        self, actor: Actor, display_key: str, *, telemetry: TelemetryContext
    ) -> UUID | RecordProblem:
        """Resolve one display key to the canonical ticket UUID."""

        outcome = _resolve_display_key(self._dsn, actor, display_key, telemetry=telemetry)
        self._emit("record.resolve_display_key", telemetry, outcome)
        return outcome

    def _emit(self, name: str, telemetry: TelemetryContext, outcome: object) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
