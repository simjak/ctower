"""Thin HTTP composition over generated boundaries and kernel Interfaces."""

from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.responses import Response

from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import BootstrapReceipt as HttpBootstrapReceipt
from ctower_client.models import (
    BootstrapRequest,
    CustodyTransferRequest,
    Problem,
    TicketCreateRequest,
    TicketResource,
    TimelineResponse,
)
from ctower_client.models import (
    TelemetryContext as HttpTelemetryContext,
)
from ctower_client.models import TicketCommandResult as HttpTicketCommandResult
from ctower_kernel.access import Access
from ctower_kernel.record import (
    Actor,
    BootstrapCommand,
    BootstrapReceipt,
    CustodyCommand,
    Record,
    RecordProblem,
    SourceReference,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

__all__ = ["create_app"]


def create_app(record: Record, *, telemetry: TelemetryRecorder | None = None) -> FastAPI:
    """Compose the private command API without embedding durable decisions."""

    app = FastAPI(title="ctower control API", version="0.0.0")
    recorder = telemetry or TelemetryRecorder()
    access = Access(record, telemetry=recorder)

    @app.middleware("http")
    async def telemetry_health(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Ctower-Telemetry-Health"] = recorder.health
        return response

    _install_bootstrap_route(app, access, recorder)
    _install_ticket_create_route(app, access, Work(record, telemetry=recorder), recorder)
    _install_custody_route(app, access, Work(record, telemetry=recorder), recorder)
    _install_ticket_read_routes(app, access, record, recorder)
    return app


def _install_bootstrap_route(
    app: FastAPI, access: Access, telemetry_recorder: TelemetryRecorder
) -> None:
    """Bind the local-only bootstrap transport Adapter."""

    @app.post("/v1/bootstrap/first-tenant", status_code=201)
    async def bootstrap_first_tenant(request: Request) -> JSONResponse:
        origin = request.client.host if request.client is not None else ""
        capability = request.headers.get("X-Ctower-Bootstrap-Capability")
        refusal = access.authorize_bootstrap(capability, origin=origin)
        if refusal is not None:
            _emit_auth_denial(telemetry_recorder, "access.authorize_bootstrap", refusal)
            return _problem_response(refusal)
        try:
            telemetry = _telemetry(request)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = BootstrapRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        if capability is None:
            raise RuntimeError("authorized bootstrap capability disappeared")
        telemetry = telemetry.bind(
            tenant_id="unresolved",
            actor_id="bootstrap-installer",
            command_id=str(command_id),
        )
        telemetry_recorder.emit(
            "access.authorize_bootstrap", telemetry, outcome="ok", reason="authorized"
        )
        outcome = access.bootstrap_first_tenant(
            BootstrapCommand(
                client_command_id=command_id,
                commander_name=payload.commander_name,
                commander_vault_ref=payload.commander_vault_ref,
                operator_credential_ref=payload.operator_credential_ref,
                operator_name=payload.operator_name,
                operator_vault_ref=payload.operator_vault_ref,
                tenant_name=payload.tenant_name,
                tenant_slug=payload.tenant_slug,
            ),
            capability=capability,
            origin=origin,
            telemetry=telemetry,
        )
        return _bootstrap_response(outcome)


def _install_ticket_create_route(
    app: FastAPI,
    access: Access,
    work: Work,
    telemetry_recorder: TelemetryRecorder,
) -> None:
    """Bind the authenticated ticket command Adapter."""

    @app.post("/v1/tickets", status_code=201)
    async def create_ticket(request: Request) -> JSONResponse:
        actor = _authenticate(access, telemetry_recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = TicketCreateRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = work.create_ticket(
            actor,
            TicketCommand(
                client_command_id=command_id,
                initial_custodian_id=payload.initial_custodian_id,
                priority=payload.priority.value,
                source=SourceReference(payload.source.kind, payload.source.ref),
                title=payload.title,
            ),
            telemetry=telemetry,
        )
        return _ticket_command_response(outcome)


def _install_ticket_read_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    telemetry_recorder: TelemetryRecorder,
) -> None:
    """Bind tenant-scoped ticket and timeline queries."""

    @app.get("/v1/tickets/{ticket_id}")
    def get_ticket(ticket_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, telemetry_recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_ticket_id = _uuid(ticket_id)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(parsed_ticket_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _ticket_response(record.get_ticket(actor, parsed_ticket_id, telemetry=telemetry))

    @app.get("/v1/tickets/{ticket_id}/timeline")
    def get_ticket_timeline(ticket_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, telemetry_recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_ticket_id = _uuid(ticket_id)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(parsed_ticket_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _timeline_response(
            record.ticket_timeline(actor, parsed_ticket_id, telemetry=telemetry)
        )


def _install_custody_route(
    app: FastAPI,
    access: Access,
    work: Work,
    telemetry_recorder: TelemetryRecorder,
) -> None:
    """Bind the protected custody command Adapter."""

    @app.post("/v1/tickets/{ticket_id}/custody")
    async def transfer_ticket_custody(ticket_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, telemetry_recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_ticket_id = _uuid(ticket_id)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = CustodyTransferRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(parsed_ticket_id),
        )
        telemetry_recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = work.transfer_custody(
            actor,
            CustodyCommand(
                client_command_id=command_id,
                expected_version=payload.expected_version,
                from_custodian_id=payload.from_custodian_id,
                protected_transfer=payload.protected_transfer,
                reason=payload.reason,
                ticket_id=parsed_ticket_id,
                to_custodian_id=payload.to_custodian_id,
            ),
            telemetry=telemetry,
        )
        return _ticket_command_response(outcome, status_code=200)


def _bootstrap_response(outcome: BootstrapReceipt | RecordProblem) -> JSONResponse:
    payload = outcome.response_payload()
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if isinstance(outcome, BootstrapReceipt):
        receipt_boundary = HttpBootstrapReceipt.model_validate_json(encoded)
        return JSONResponse(status_code=201, content=receipt_boundary.model_dump(mode="json"))
    return _problem_response(outcome)


def _ticket_command_response(
    outcome: TicketCommandResult | RecordProblem, *, status_code: int = 201
) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = HttpTicketCommandResult.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=status_code, content=boundary.model_dump(mode="json"))


def _ticket_response(outcome: Ticket | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = TicketResource.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))


def _timeline_response(outcome: TicketTimeline | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = TimelineResponse.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))


def _problem_response(problem: RecordProblem) -> JSONResponse:
    problem_boundary = Problem.model_validate_json(_encoded(problem.response_payload()))
    return JSONResponse(
        status_code=problem.status,
        content=problem_boundary.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )


def _encoded(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _uuid(value: str | None) -> UUID:
    if value is None:
        raise ValueError("UUID transport value is missing")
    return UUID(value)


def _validation_problem() -> RecordProblem:
    return RecordProblem(
        code="validation-error",
        detail="The request body or transport identifier does not match the authored contract.",
        status=422,
        title="Request validation failed",
    )


def _telemetry(request: Request) -> TelemetryContext:
    payload = request.headers.get("X-Ctower-Telemetry-Context")
    if payload is None:
        raise ValueError("telemetry context is missing")
    return _trusted_telemetry(HttpTelemetryContext.model_validate_json(payload))


def _trusted_telemetry(context: HttpTelemetryContext) -> TelemetryContext:
    return TelemetryContext(
        schema=context.schema_id,
        trace_id=context.trace_id,
        span_id=context.span_id,
        trace_flags=context.trace_flags,
        trace_state=context.trace_state,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        command_id=context.command_id,
        ticket_id=context.ticket_id,
        workflow_run_id=context.workflow_run_id,
        stage_attempt_id=context.stage_attempt_id,
        job_id=context.job_id,
        runner_id=context.runner_id,
        fencing_token=context.fencing_token,
        effect_id=context.effect_id,
        component_revision_id=context.component_revision_id,
        deployment_id=context.deployment_id,
    )


def _authenticate(
    access: Access, recorder: TelemetryRecorder, request: Request
) -> Actor | RecordProblem:
    outcome = access.authenticate(request.headers.get("Authorization"))
    if isinstance(outcome, RecordProblem):
        _emit_auth_denial(recorder, "access.authenticate", outcome)
    return outcome


def _emit_auth_denial(recorder: TelemetryRecorder, name: str, problem: RecordProblem) -> None:
    recorder.emit(
        name,
        _denial_telemetry(),
        outcome="error",
        reason=problem.code,
    )


def _denial_telemetry() -> TelemetryContext:
    correlation_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=secrets.token_hex(16),
        span_id=secrets.token_hex(8),
        trace_flags=0,
        correlation_id=correlation_id,
        causation_id=correlation_id,
        tenant_id="unauthenticated",
        actor_id="unauthenticated",
        command_id=correlation_id,
    )
