"""One fail-closed HTTP durability envelope for every command Module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ctower_api._http_support import encoded, problem_response
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["mutation_response"]


class _SemanticResult(Protocol):
    def response_payload(self) -> dict[str, object]: ...


def mutation_response(
    record: Record,
    outcome: _SemanticResult | RecordProblem,
    *,
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    telemetry: TelemetryContext,
    boundary_model: type[BaseModel],
    accepted_status: int,
) -> JSONResponse:
    """Keep semantic bytes stable while overlaying only Record's durability decision."""

    if isinstance(outcome, RecordProblem):
        return problem_response(outcome)
    decision = record.reconcile_durability(
        tenant_id,
        principal_id,
        command_id,
        now=_observed_time(),
        telemetry=telemetry,
    )
    if isinstance(decision, RecordProblem):
        return problem_response(decision)
    payload = cast(
        dict[str, object],
        _durability_overlay(outcome.response_payload(), decision.state.value),
    )
    boundary = boundary_model.model_validate_json(encoded(payload))
    if decision.accepted:
        return JSONResponse(status_code=accepted_status, content=boundary.model_dump(mode="json"))
    return JSONResponse(
        status_code=202,
        content=boundary.model_dump(mode="json"),
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def _durability_overlay(value: object, state: str) -> object:
    if isinstance(value, dict):
        return {
            key: state if key == "durability_state" else _durability_overlay(item, state)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_durability_overlay(item, state) for item in value]
    return value


def _observed_time() -> datetime:
    return datetime.now(UTC)
