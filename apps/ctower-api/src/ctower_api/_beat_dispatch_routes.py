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
)
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import BeatDispatchEffectList, BeatRoutineList
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.runtime.beats import BeatDispatchEffect, BeatRoutine

__all__: tuple[str, ...] = ()


class BeatDispatchRuntime(Protocol):
    def list_beat_dispatches(self, actor: Actor) -> tuple[BeatDispatchEffect, ...]: ...

    def list_beat_routines(self, actor: Actor) -> tuple[BeatRoutine, ...]: ...


def install_beat_dispatch_routes(
    app: FastAPI,
    access: Access,
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
