"""Authenticated HTTP adapter for append-only ticket comments."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import ticket_uuid as _ticket_uuid
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import TicketCommentRequest
from ctower_client.models import TicketCommentResult as HttpTicketCommentResult
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.comments import TicketCommentCommand
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def install_comment_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install the authenticated append-only comment command."""

    @app.post("/v1/tickets/{ticket_id}/comments")
    async def add_comment(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, record, recorder, request, ticket_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, command, telemetry = parsed
        outcome = record.add_comment(
            actor,
            command,
            request_digest=hashlib.sha256(
                json.dumps(
                    command.request_payload(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).digest(),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command.client_command_id,
            telemetry=telemetry,
            boundary_model=HttpTicketCommentResult,
            accepted_status=200,
        )


async def _parse(
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
    request: Request,
    ticket_id: str,
) -> tuple[Actor, TicketCommentCommand, TelemetryContext] | JSONResponse:
    actor = _authenticate(
        access,
        recorder,
        request,
        required_scope=CredentialScope.CAPTURE,
    )
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        payload = TicketCommentRequest.model_validate_json(await request.body())
        context = _telemetry(request)
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    parsed_ticket_id = _ticket_uuid(record, actor, ticket_id, telemetry=context)
    if isinstance(parsed_ticket_id, RecordProblem):
        return _problem_response(parsed_ticket_id)
    telemetry = context.bind(
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
        ticket_id=str(parsed_ticket_id),
    )
    try:
        command = TicketCommentCommand(command_id, parsed_ticket_id, payload.body)
    except ValueError:
        return _problem_response(
            RecordProblem(
                code="ticket-comment-invalid",
                detail="Comment body must contain bounded visible text.",
                status=422,
                title="Ticket comment invalid",
                command_id=command_id,
            )
        )
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, command, telemetry
