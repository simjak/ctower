"""Strict HTTP adapter for Work-owned Request capture and contextual reads."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

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
    RequestBlockerRequest,
    RequestCaptureRequest,
    RequestCaptureResult,
    RequestChangeResult,
    RequestClosureEvaluationRequest,
    RequestList,
    RequestOwnerRequest,
    RequestPriorityRequest,
    RequestTicketRelationRequest,
    RequestTriageRequest,
)
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    RequestBlocker,
    RequestCapture,
    RequestClosureEvaluation,
    RequestOwner,
    RequestPriority,
    Requests,
    RequestTicketRelation,
    RequestTriage,
)
from ctower_kernel.work.requests import RequestCaptureResult as SemanticRequestCaptureResult
from ctower_kernel.work.requests import RequestChangeResult as SemanticRequestChangeResult

__all__: tuple[str, ...] = ()

_BODY_LIMIT = 128 * 1024
_MutationOutcome = SemanticRequestCaptureResult | SemanticRequestChangeResult | RecordProblem


@dataclass(frozen=True, slots=True)
class _ParsedMutation:
    actor: Actor
    command_id: UUID
    payload: BaseModel
    telemetry: TelemetryContext


class _RequestRoutes:
    def __init__(
        self,
        access: Access,
        record: Record,
        requests: Requests,
        recorder: TelemetryRecorder,
    ) -> None:
        self._access = access
        self._record = record
        self._requests = requests
        self._recorder = recorder

    async def capture(self, request: Request) -> JSONResponse:
        parsed = await self._mutation(request, CredentialScope.CAPTURE, RequestCaptureRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        payload = parsed.payload
        if not isinstance(payload, RequestCaptureRequest):
            raise TypeError("Request capture parser returned the wrong boundary")
        outcome = self._requests.capture(
            parsed.actor,
            RequestCapture(parsed.command_id, payload.project_key, payload.text),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, RequestCaptureResult, accepted_status=201)

    async def list_requests(self, request: Request, project_key: str | None = None) -> JSONResponse:
        actor = authenticate(
            self._access,
            self._recorder,
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
        outcome = self._requests.list(actor, project_key=project_key, telemetry=telemetry)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = RequestList.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    async def prioritize(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestPriorityRequest)

    async def triage(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestTriageRequest)

    async def assign_owner(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestOwnerRequest)

    async def relate_ticket(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestTicketRelationRequest)

    async def set_blocker(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestBlockerRequest)

    async def evaluate_closure(self, request: Request, request_id: UUID) -> JSONResponse:
        return await self._change(request, request_id, RequestClosureEvaluationRequest)

    async def _change(
        self, request: Request, request_id: UUID, boundary_model: type[BaseModel]
    ) -> JSONResponse:
        parsed = await self._mutation(request, CredentialScope.TRANSITION, boundary_model)
        if isinstance(parsed, JSONResponse):
            return parsed
        outcome = _apply_change(self._requests, parsed, request_id)
        return self._response(parsed, outcome, RequestChangeResult, accepted_status=200)

    async def _mutation(
        self,
        request: Request,
        scope: CredentialScope,
        boundary_model: type[BaseModel],
    ) -> _ParsedMutation | JSONResponse:
        actor = authenticate(self._access, self._recorder, request, required_scope=scope)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            payload = boundary_model.model_validate_json(await _bounded_body(request))
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        self._recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _ParsedMutation(actor, command_id, payload, telemetry)

    def _response(
        self,
        parsed: _ParsedMutation,
        outcome: _MutationOutcome,
        boundary_model: type[BaseModel],
        *,
        accepted_status: int,
    ) -> JSONResponse:
        return mutation_response(
            self._record,
            outcome,
            tenant_id=parsed.actor.tenant_id,
            principal_id=parsed.actor.principal_id,
            command_id=parsed.command_id,
            telemetry=parsed.telemetry,
            boundary_model=boundary_model,
            accepted_status=accepted_status,
        )


async def _bounded_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > _BODY_LIMIT:
        raise ValueError("request body exceeds bounded envelope")
    return body


def _apply_change(
    authority: Requests, parsed: _ParsedMutation, request_id: UUID
) -> _MutationOutcome:
    actor, command_id, payload, telemetry = (
        parsed.actor,
        parsed.command_id,
        parsed.payload,
        parsed.telemetry,
    )
    if isinstance(payload, RequestPriorityRequest):
        return authority.prioritize(
            actor,
            RequestPriority(
                command_id, request_id, payload.expected_version, payload.priority, payload.reason
            ),
            telemetry=telemetry,
        )
    if isinstance(payload, RequestTriageRequest):
        command = RequestTriage(
            command_id,
            request_id,
            payload.expected_version,
            payload.disposition,
            payload.reason,
            payload.canonical_request_id,
        )
        return authority.triage(actor, command, telemetry=telemetry)
    if isinstance(payload, RequestOwnerRequest):
        return authority.assign_owner(
            actor,
            RequestOwner(
                command_id, request_id, payload.expected_version, payload.owner_id, payload.reason
            ),
            telemetry=telemetry,
        )
    if isinstance(payload, RequestTicketRelationRequest):
        return authority.relate_ticket(
            actor,
            RequestTicketRelation(
                command_id,
                request_id,
                payload.expected_version,
                payload.ticket_id,
                payload.purpose,
                payload.active,
                payload.reason,
            ),
            telemetry=telemetry,
        )
    if isinstance(payload, RequestBlockerRequest):
        return authority.set_blocker(
            actor,
            RequestBlocker(
                command_id,
                request_id,
                payload.expected_version,
                payload.blocker_key,
                payload.active,
                payload.reason,
            ),
            telemetry=telemetry,
        )
    if isinstance(payload, RequestClosureEvaluationRequest):
        return authority.evaluate_closure(
            actor,
            RequestClosureEvaluation(
                command_id, request_id, payload.expected_version, payload.reason
            ),
            telemetry=telemetry,
        )
    raise TypeError("Request operation has no authored payload")


def install_request_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    requests: Requests,
    recorder: TelemetryRecorder,
) -> None:
    """Install the Phase-1 Request command and accepted-only read seams."""

    routes = _RequestRoutes(access, record, requests, recorder)
    app.add_api_route("/v1/requests", routes.capture, methods=["POST"], status_code=201)
    app.add_api_route("/v1/requests", routes.list_requests, methods=["GET"])
    app.add_api_route("/v1/requests/{request_id}/priority", routes.prioritize, methods=["POST"])
    app.add_api_route("/v1/requests/{request_id}/triage", routes.triage, methods=["POST"])
    app.add_api_route("/v1/requests/{request_id}/owner", routes.assign_owner, methods=["POST"])
    app.add_api_route(
        "/v1/requests/{request_id}/ticket-relations", routes.relate_ticket, methods=["POST"]
    )
    app.add_api_route("/v1/requests/{request_id}/blockers", routes.set_blocker, methods=["POST"])
    app.add_api_route(
        "/v1/requests/{request_id}/closure-evaluations",
        routes.evaluate_closure,
        methods=["POST"],
    )
