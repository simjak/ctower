"""Authenticated HTTP adapters for the Board card context-set write facts."""

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
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import ApplyLabelRequest, ChangeReferenceRequest
from ctower_client.models import ApplyLabelResult as HttpApplyLabelResult
from ctower_client.models import ChangeReferenceResult as HttpChangeReferenceResult
from ctower_kernel.access import Access
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.change_references import ChangeReferenceCommand
from ctower_kernel.board_context.labels import ApplyLabelCommand
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope

__all__: tuple[str, ...] = ()


def install_board_context_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    board_context: BoardContextFacts,
    recorder: TelemetryRecorder,
) -> None:
    """Install the authenticated Change-reference and apply-label commands."""

    _install_change_reference_route(app, access, record, board_context, recorder)
    _install_apply_label_route(app, access, record, board_context, recorder)


def _install_change_reference_route(
    app: FastAPI,
    access: Access,
    record: Record,
    board_context: BoardContextFacts,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/change-references")
    async def record_change_reference(ticket_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_ticket_id = _uuid(ticket_id)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = ChangeReferenceRequest.model_validate_json(await request.body())
            command = ChangeReferenceCommand(
                command_id,
                parsed_ticket_id,
                payload.repository,
                payload.change_identity,
                payload.reference,
            )
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(parsed_ticket_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = board_context.record_change_reference(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
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
            boundary_model=HttpChangeReferenceResult,
            accepted_status=200,
        )


def _install_apply_label_route(
    app: FastAPI,
    access: Access,
    record: Record,
    board_context: BoardContextFacts,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/labels")
    async def apply_label(ticket_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_ticket_id = _uuid(ticket_id)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = ApplyLabelRequest.model_validate_json(await request.body())
            command = ApplyLabelCommand(command_id, parsed_ticket_id, payload.label_key)
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(parsed_ticket_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = board_context.apply_label(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
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
            boundary_model=HttpApplyLabelResult,
            accepted_status=200,
        )


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
