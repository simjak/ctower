"""Cohesive tenant-scoped ticket read boundary for both authored reference forms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from ctower_kernel.record.interface import Actor, RecordProblem, Ticket, TicketTimeline
    from ctower_kernel.telemetry import TelemetryContext

__all__ = ["TicketStore"]


class TicketStore(Protocol):
    """Read one ticket, its timeline, or the UUID a display key stands for.

    A reference is either the canonical UUID or the server-assigned `PREFIX-N`
    handle. Both forms answer inside the caller's authorized Project scope only.
    """

    def get(
        self,
        actor: Actor,
        reference: UUID | str,
        project_key: str,
        *,
        telemetry: TelemetryContext,
    ) -> Ticket | RecordProblem: ...

    def timeline(
        self,
        actor: Actor,
        reference: UUID | str,
        project_key: str,
        *,
        telemetry: TelemetryContext,
    ) -> TicketTimeline | RecordProblem: ...

    def resolve_display_key(
        self, actor: Actor, display_key: str, *, telemetry: TelemetryContext
    ) -> UUID | RecordProblem: ...
