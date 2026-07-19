"""Strict frozen propagation context and stable telemetry signal Interface."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Protocol
from uuid import UUID

__all__ = ["NoopTelemetry", "Telemetry", "TelemetryContext", "TelemetryRecord"]

_TRACE_ID = re.compile(r"^[a-f0-9]{32}$")
_SPAN_ID = re.compile(r"^[a-f0-9]{16}$")
_MAX_TRACE_FLAGS = 255
_MAX_TRACE_STATE = 512
_MAX_IDENTITY = 128
_REQUIRED = {
    "schema",
    "trace_id",
    "span_id",
    "trace_flags",
    "correlation_id",
    "causation_id",
    "tenant_id",
    "actor_id",
    "command_id",
}
_OPTIONAL = {
    "trace_state",
    "ticket_id",
    "workflow_run_id",
    "stage_attempt_id",
    "job_id",
    "runner_id",
    "fencing_token",
    "effect_id",
    "component_revision_id",
    "deployment_id",
}


@dataclass(frozen=True, slots=True)
class TelemetryContext:
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

    def __post_init__(self) -> None:
        _validate_trace_fields(self)
        for required_value in (
            self.correlation_id,
            self.causation_id,
            self.tenant_id,
            self.actor_id,
            self.command_id,
        ):
            _validate_id(required_value)
        _validate_optional_fields(self)

    @classmethod
    def from_json(cls, payload: bytes) -> TelemetryContext:
        value: object = json.loads(payload)
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ValueError("telemetry context must be a JSON object")
        fields = set(value)
        if not fields >= _REQUIRED or fields - (_REQUIRED | _OPTIONAL):
            raise ValueError("telemetry context fields do not match the authored contract")
        return cls(
            schema=_required_string(value, "schema"),
            trace_id=_required_string(value, "trace_id"),
            span_id=_required_string(value, "span_id"),
            trace_flags=_required_integer(value, "trace_flags"),
            correlation_id=_required_string(value, "correlation_id"),
            causation_id=_required_string(value, "causation_id"),
            tenant_id=_required_string(value, "tenant_id"),
            actor_id=_required_string(value, "actor_id"),
            command_id=_required_string(value, "command_id"),
            trace_state=_optional_string(value, "trace_state"),
            ticket_id=_optional_string(value, "ticket_id"),
            workflow_run_id=_optional_string(value, "workflow_run_id"),
            stage_attempt_id=_optional_string(value, "stage_attempt_id"),
            job_id=_optional_string(value, "job_id"),
            runner_id=_optional_string(value, "runner_id"),
            fencing_token=_optional_integer(value, "fencing_token"),
            effect_id=_optional_string(value, "effect_id"),
            component_revision_id=_optional_string(value, "component_revision_id"),
            deployment_id=_optional_string(value, "deployment_id"),
        )

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


def _validate_trace_fields(context: TelemetryContext) -> None:
    if context.schema != "ctower.telemetry-context/v1":
        raise ValueError("unsupported telemetry context schema")
    if _TRACE_ID.fullmatch(context.trace_id) is None:
        raise ValueError("invalid telemetry trace identifier")
    if _SPAN_ID.fullmatch(context.span_id) is None:
        raise ValueError("invalid telemetry span identifier")
    if not 0 <= context.trace_flags <= _MAX_TRACE_FLAGS:
        raise ValueError("invalid telemetry trace flags")


def _validate_optional_fields(context: TelemetryContext) -> None:
    for optional_value in (
        context.ticket_id,
        context.workflow_run_id,
        context.stage_attempt_id,
        context.job_id,
        context.runner_id,
        context.effect_id,
        context.component_revision_id,
        context.deployment_id,
    ):
        if optional_value is not None:
            _validate_id(optional_value)
    if context.trace_state is not None and len(context.trace_state) > _MAX_TRACE_STATE:
        raise ValueError("telemetry trace state is too long")
    if context.fencing_token is not None and context.fencing_token < 1:
        raise ValueError("invalid telemetry fencing token")


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


def _validate_id(value: str) -> None:
    if not 1 <= len(value) <= _MAX_IDENTITY:
        raise ValueError("telemetry identity is outside the authored bounds")


def _required_string(value: dict[object, object], key: str) -> str:
    field = value.get(key)
    if not isinstance(field, str):
        raise TypeError(f"telemetry field {key} must be a string")
    return field


def _optional_string(value: dict[object, object], key: str) -> str | None:
    field = value.get(key)
    if field is not None and not isinstance(field, str):
        raise ValueError(f"telemetry field {key} must be a string or null")
    return field


def _required_integer(value: dict[object, object], key: str) -> int:
    field = value.get(key)
    if not isinstance(field, int) or isinstance(field, bool):
        raise TypeError(f"telemetry field {key} must be an integer")
    return field


def _optional_integer(value: dict[object, object], key: str) -> int | None:
    field = value.get(key)
    if field is not None and (not isinstance(field, int) or isinstance(field, bool)):
        raise ValueError(f"telemetry field {key} must be an integer or null")
    return field
