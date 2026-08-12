"""HTTP boundary for immutable fleet-beat routines and emitted effects."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    BeatDispatchEffectList,
    BeatRoutineList,
)
from ctower_client.models import (
    BeatRoutineRetirementReceipt as HttpBeatRoutineRetirementReceipt,
)
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.runtime.beats import BeatDispatchEffect, BeatRoutine
from ctower_kernel.runtime.retirement import (
    BeatRoutineRetireCommand,
    BeatRoutineRetirementReceipt,
)

__all__: tuple[str, ...] = ()


class BeatDispatchRuntime(Protocol):
    def list_beat_dispatches(self, actor: Actor) -> tuple[BeatDispatchEffect, ...]: ...

    def list_beat_routines(self, actor: Actor) -> tuple[BeatRoutine, ...]: ...

    def retire_beat_routine(
        self, actor: Actor, command: BeatRoutineRetireCommand
    ) -> BeatRoutineRetirementReceipt | RecordProblem: ...


def install_beat_dispatch_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    runtime: BeatDispatchRuntime,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/runtime/beat-dispatches")
    def list_beat_dispatches(request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        boundary = BeatDispatchEffectList.model_validate_json(
            encoded(
                {
                    "effects": [
                        effect.response_payload() for effect in runtime.list_beat_dispatches(actor)
                    ]
                }
            )
        )
        return JSONResponse(content=boundary.model_dump(mode="json"))

    @app.post("/v1/runtime/beat-routines/{routine_ref}/retire")
    async def retire_beat_routine(routine_ref: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        if await request.body() != b"":
            return problem_response(validation_problem())
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            command = BeatRoutineRetireCommand(command_id, routine_ref)
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
        except ValueError:
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = runtime.retire_beat_routine(actor, command)
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpBeatRoutineRetirementReceipt,
            accepted_status=200,
        )

    @app.get("/v1/runtime/beat-routines")
    def list_beat_routines(request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        boundary = BeatRoutineList.model_validate_json(
            encoded(
                {
                    "routines": [
                        routine.response_payload() for routine in runtime.list_beat_routines(actor)
                    ]
                }
            )
        )
        return JSONResponse(content=boundary.model_dump(mode="json"))
