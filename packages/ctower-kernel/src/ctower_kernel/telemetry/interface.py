"""Strict frozen propagation context and stable telemetry signal Interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Protocol
from uuid import UUID

__all__ = ["NoopTelemetry", "Telemetry", "TelemetryContext", "TelemetryRecord"]


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    """Framework-free value built only from trusted or generated-validated fields."""

    schema: str
    trace_id: str
    span_id: str
    trace_flags: int
    correlation_id: str
    causation_id: str
    tenant_id: str
    actor_id: str
    command_id: str
    trace_state: str | None = None
    ticket_id: str | None = None
    workflow_run_id: str | None = None
    stage_attempt_id: str | None = None
    job_id: str | None = None
    runner_id: str | None = None
    fencing_token: int | None = None
    effect_id: str | None = None
    component_revision_id: str | None = None
    deployment_id: str | None = None

    def bind(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        command_id: str | None = None,
        ticket_id: str | None = None,
    ) -> TelemetryContext:
        return replace(
            self,
            tenant_id=tenant_id,
            actor_id=actor_id,
            command_id=command_id or self.command_id,
            ticket_id=ticket_id if ticket_id is not None else self.ticket_id,
        )

    def to_mapping(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def correlation_uuid(self, fallback: UUID) -> UUID:
        try:
            return UUID(self.correlation_id)
        except ValueError:
            return fallback


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    signal: str
    name: str
    context: TelemetryContext
    outcome: str
    reason: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": "ctower.telemetry-record/v1",
            "signal": self.signal,
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "correlation_id": self.context.correlation_id,
            "causation_id": self.context.causation_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "metric_labels": {"outcome": self.outcome, "reason": self.reason},
        }


class Telemetry(Protocol):
    def emit(self, name: str, context: TelemetryContext, *, outcome: str, reason: str) -> None:
        """Emit compatible span, log, and metric signals without affecting authority."""

        ...


class NoopTelemetry:
    def emit(self, name: str, context: TelemetryContext, *, outcome: str, reason: str) -> None:
        del name, context, outcome, reason
