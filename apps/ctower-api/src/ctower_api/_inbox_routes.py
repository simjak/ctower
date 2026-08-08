"""Authenticated HTTP adapter for the native two-party inbox."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

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
    InboxAcknowledgeRequest,
    InboxPromotionRequest,
    InboxReadState,
    InboxSendRequest,
)
from ctower_client.models import InboxAcknowledgeResult as HttpInboxAcknowledgeResult
from ctower_client.models import InboxPromotionResult as HttpInboxPromotionResult
from ctower_client.models import InboxSendResult as HttpInboxSendResult
from ctower_client.models import InboxThread as HttpInboxThread
from ctower_client.models import InboxThreadList as HttpInboxThreadList
from ctower_kernel.access import Access
from ctower_kernel.inbox import (
    Inbox,
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxPromotionCommand,
    InboxSendCommand,
)
from ctower_kernel.projections import Projections
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope

__all__: tuple[str, ...] = ()


def install_inbox_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    inbox: Inbox,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    _install_send_route(app, access, record, inbox, recorder)
    _install_acknowledge_route(app, access, record, inbox, recorder)
    _install_promotion_route(app, access, record, inbox, recorder)
    _install_list_route(app, access, projections, recorder)
    _install_read_state_route(app, access, projections, recorder)
    _install_read_route(app, access, projections, recorder)


def _install_acknowledge_route(
    app: FastAPI,
    access: Access,
    record: Record,
    inbox: Inbox,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/inbox/messages/{message_id}/ack")
    async def acknowledge(message_id: str, request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.TRANSITION)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            parsed_message_id = uuid_value(message_id)
            payload = InboxAcknowledgeRequest.model_validate_json(await request.body())
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            command = InboxAcknowledgeCommand(
                command_id,
                parsed_message_id,
                InboxAcknowledgementState(payload.state),
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = inbox.acknowledge(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpInboxAcknowledgeResult,
            accepted_status=200,
        )


def _install_send_route(
    app: FastAPI,
    access: Access,
    record: Record,
    inbox: Inbox,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/inbox/messages", status_code=201)
    async def send(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = InboxSendRequest.model_validate_json(await request.body())
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            command = InboxSendCommand(command_id, payload.to, payload.text, payload.thread_id)
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = inbox.send(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpInboxSendResult,
            accepted_status=201,
        )


def _install_promotion_route(
    app: FastAPI,
    access: Access,
    record: Record,
    inbox: Inbox,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/inbox/threads/{thread_id}/promotion")
    async def promote(thread_id: str, request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            parsed_thread_id = uuid_value(thread_id)
            payload = InboxPromotionRequest.model_validate_json(await request.body())
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            command = InboxPromotionCommand(command_id, parsed_thread_id, payload.ticket_id)
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = inbox.promote(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpInboxPromotionResult,
            accepted_status=200,
        )


def _install_list_route(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/inbox/threads")
    def list_inbox(request: Request, *, unread: bool = False) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        result = projections.list_inbox(actor, unread=unread)
        boundary = HttpInboxThreadList.model_validate_json(encoded(result.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _install_read_route(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/inbox/threads/{thread_id}")
    def read_inbox(thread_id: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            parsed_thread_id = uuid_value(thread_id)
        except ValueError:
            return problem_response(validation_problem())
        result = projections.read_inbox(actor, parsed_thread_id)
        if result is None:
            return problem_response(
                RecordProblem(
                    "tenant-scope-denied",
                    "The requested inbox thread is unavailable in the authenticated scope.",
                    404,
                    "Inbox thread unavailable",
                )
            )
        boundary = HttpInboxThread.model_validate_json(encoded(result.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _install_read_state_route(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/inbox/threads/{thread_id}/read-state")
    def read_state(thread_id: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            parsed_thread_id = uuid_value(thread_id)
        except ValueError:
            return problem_response(validation_problem())
        result = projections.inbox_read_state(actor, parsed_thread_id)
        if result is None:
            return problem_response(
                RecordProblem(
                    "tenant-scope-denied",
                    "The requested inbox thread is unavailable in the authenticated scope.",
                    404,
                    "Inbox thread unavailable",
                )
            )
        boundary = InboxReadState.model_validate_json(encoded(result.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
