"""One fail-closed HTTP durability envelope for every command Module."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, cast, runtime_checkable
from uuid import UUID

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ctower_api._http_support import encoded, problem_response
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["mutation_response"]


@runtime_checkable
class _SemanticResult(Protocol):
    def response_payload(self) -> Mapping[str, object]: ...


def mutation_response(
    record: Record,
    outcome: BaseModel | _SemanticResult | RecordProblem,
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
        _durability_overlay(
            (
                outcome.response_payload()
                if isinstance(outcome, _SemanticResult)
                else outcome.model_dump(mode="json", by_alias=True)
            ),
            decision.state.value,
            decision.acceptance_position,
        ),
    )
    boundary = boundary_model.model_validate_json(encoded(payload))
    # `by_alias` is what makes the wire name the authored one. A boundary field
    # whose contract name is a Python keyword — `InboxSendResult.from` — carries
    # an alias, and dumping without it puts `from_` on the wire against an
    # `additionalProperties: false` schema. The generated clients accept either
    # spelling by name, so only a strict reader outside them sees it.
    envelope = boundary.model_dump(mode="json", by_alias=True)
    if decision.accepted:
        return JSONResponse(status_code=accepted_status, content=envelope)
    return JSONResponse(
        status_code=202,
        content=envelope,
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def _durability_overlay(value: object, state: str, accepted_position: int | None) -> object:
    if isinstance(value, dict):
        return {
            key: (
                state
                if key == "durability_state"
                else accepted_position
                if key == "accepted_position"
                else _durability_overlay(item, state, accepted_position)
            )
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_durability_overlay(item, state, accepted_position) for item in value]
    return value


def _observed_time() -> datetime:
    return datetime.now(UTC)
