"""Strict HTTP adapter for Work-owned Request capture and contextual reads."""

from __future__ import annotations

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
from ctower_client.models import RequestCaptureRequest, RequestCaptureResult, RequestList
from ctower_kernel.access import Access
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.work.requests import RequestCapture, Requests

__all__: tuple[str, ...] = ()

_BODY_LIMIT = 128 * 1024


def install_request_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    requests: Requests,
    recorder: TelemetryRecorder,
) -> None:
    """Install the two v1 channels' single command and accepted-only read seam."""

    @app.post("/v1/requests", status_code=201)
    async def capture(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            body = await request.body()
            if len(body) > _BODY_LIMIT:
                raise ValueError("request body exceeds bounded envelope")
            payload = RequestCaptureRequest.model_validate_json(body)
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = requests.capture(
            actor,
            RequestCapture(command_id, payload.project_key, payload.text),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=RequestCaptureResult,
            accepted_status=201,
        )

    @app.get("/v1/requests")
    async def list_requests(request: Request, project_key: str | None = None) -> JSONResponse:
        actor = authenticate(
            access,
            recorder,
            request,
            required_scope=UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id), actor_id=str(actor.principal_id)
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        outcome = requests.list(actor, project_key=project_key, telemetry=telemetry)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = RequestList.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))
