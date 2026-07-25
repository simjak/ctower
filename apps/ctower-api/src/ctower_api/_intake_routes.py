"""Authenticated HTTP adapter for explicit thread-first intake commands."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import (
    authenticate,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import IntakeCommandResult as HttpIntakeCommandResult
from ctower_client.models import IntakePromotionRequest, IntakeSubmitRequest
from ctower_kernel.access import Access
from ctower_kernel.record import (
    InboundSource,
    IntakeIntent,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    Record,
    RecordProblem,
)
from ctower_kernel.record.intake import IntakeTaint
from ctower_kernel.work import Intake

__all__: tuple[str, ...] = ()


def install_intake_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    intake: Intake,
    recorder: TelemetryRecorder,
) -> None:
    """Install the single submit operation and explicit later promotion."""

    _install_submit_route(app, access, record, intake, recorder)
    _install_promotion_route(app, access, record, intake, recorder)


def _install_submit_route(
    app: FastAPI,
    access: Access,
    record: Record,
    intake: Intake,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/intake", status_code=201)
    async def submit(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = IntakeSubmitRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = intake.submit(
            actor,
            IntakeSubmitCommand(
                client_command_id=command_id,
                project_key=payload.project_key,
                source=InboundSource(payload.source.kind, payload.source.ref),
                content=payload.content,
                intent=IntakeIntent(
                    payload.intent.value if payload.intent is not None else "discussion"
                ),
                taint=IntakeTaint(
                    payload.taint.value if payload.taint is not None else "authenticated"
                ),
                thread_id=payload.thread_id,
                expected_thread_version=payload.expected_thread_version,
                initial_custodian_id=payload.initial_custodian_id,
                priority=payload.priority.value if payload.priority is not None else None,
                title=payload.title,
                target_ticket_id=payload.target_ticket_id,
                expected_ticket_version=payload.expected_ticket_version,
            ),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpIntakeCommandResult,
            accepted_status=201,
        )


def _install_promotion_route(
    app: FastAPI,
    access: Access,
    record: Record,
    intake: Intake,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/intake/events/{inbound_event_id}/promotion")
    async def promote(inbound_event_id: str, request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            event_id = uuid_value(inbound_event_id)
            payload = IntakePromotionRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = intake.promote(
            actor,
            IntakePromotionCommand(
                client_command_id=command_id,
                inbound_event_id=event_id,
                expected_thread_version=payload.expected_thread_version,
                intent=IntakeIntent(payload.intent.value),
                initial_custodian_id=payload.initial_custodian_id,
                priority=payload.priority.value if payload.priority is not None else None,
                title=payload.title,
                target_ticket_id=payload.target_ticket_id,
                expected_ticket_version=payload.expected_ticket_version,
            ),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpIntakeCommandResult,
            accepted_status=200,
        )
