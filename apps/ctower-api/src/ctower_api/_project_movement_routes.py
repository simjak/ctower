"""Authenticated HTTP adapter for the project movement read (transition facts)."""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import MovementEventPage as HttpMovementEventPage
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.movement_events import MovementEventPage

__all__: tuple[str, ...] = ()

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_DEFAULT_LIMIT = 50


def install_project_movement_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install the read-only project movement view (transition facts only)."""

    @app.get("/v1/projects/{project_key}/movement")
    def list_ticket_movement(
        project_key: str,
        request: Request,
        cursor: int = 0,
        limit: int = _DEFAULT_LIMIT,
    ) -> JSONResponse:
        actor = _read_actor(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_project_key = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = record.event_audit.movement_events(
            actor, parsed_project_key, cursor=cursor, limit=limit, telemetry=telemetry
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        return _read_response(outcome)


def _read_actor(
    access: Access, recorder: TelemetryRecorder, request: Request
) -> Actor | RecordProblem:
    return _authenticate(
        access,
        recorder,
        request,
        required_scope=_UnscopedAuthentication.ALLOWED,
    )


def _read_response(outcome: MovementEventPage) -> JSONResponse:
    boundary = HttpMovementEventPage.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))


def _project_key(value: str) -> str:
    if _PROJECT_KEY.fullmatch(value) is None:
        raise ValueError("invalid project key")
    return value
