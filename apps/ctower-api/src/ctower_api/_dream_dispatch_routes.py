"""HTTP boundary for nightly dream effects and output custody."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    DreamDispatchConsumeRequest,
    DreamDispatchEffectList,
)
from ctower_client.models import (
    DreamDispatchReceipt as HttpDreamDispatchReceipt,
)
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.runtime import (
    DreamDispatchConsumeCommand,
    DreamDispatchEffect,
    DreamDispatchReceipt,
)

__all__: tuple[str, ...] = ()


class DreamDispatchRuntime(Protocol):
    def list_dream_dispatches(self, actor: Actor) -> tuple[DreamDispatchEffect, ...]: ...

    def consume_dream_dispatch(
        self, actor: Actor, command: DreamDispatchConsumeCommand
    ) -> DreamDispatchReceipt | RecordProblem: ...


def install_dream_dispatch_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    runtime: DreamDispatchRuntime,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/runtime/dream-dispatches")
    def list_dream_dispatches(request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        effects = runtime.list_dream_dispatches(actor)
        boundary = DreamDispatchEffectList.model_validate_json(
            encoded({"effects": [effect.response_payload() for effect in effects]})
        )
        return JSONResponse(content=boundary.model_dump(mode="json"))

    @app.post("/v1/runtime/dream-dispatches/{effect_id}/consume")
    async def consume_dream_dispatch(effect_id: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            parsed_effect = uuid_value(effect_id)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = DreamDispatchConsumeRequest.model_validate_json(await request.body())
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = runtime.consume_dream_dispatch(
            actor,
            DreamDispatchConsumeCommand(command_id, parsed_effect, payload.output_digest),
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpDreamDispatchReceipt,
            accepted_status=200,
        )
