"""Authenticated HTTP adapter for recorded work sessions."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import ticket_uuid as _ticket_uuid
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import ProjectSessionPage as HttpProjectSessionPage
from ctower_client.models import (
    SessionCloseFact,
    SessionFactRequest,
    SessionStartRequest,
    SessionTransitionFact,
)
from ctower_client.models import SessionReceipt as HttpSessionReceipt
from ctower_client.models import TicketSessionList as HttpTicketSessionList
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.session_events import SessionOutcome, SessionState
from ctower_kernel.record.sessions import (
    ProjectSessionPage,
    SessionCloseCommand,
    SessionFactCommand,
    SessionReceipt,
    SessionStartCommand,
    SessionTransitionCommand,
    TicketSessionList,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_DEFAULT_LIMIT = 50


def install_session_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install the append-only work-session commands and their scoped reads."""

    _install_session_commands(app, access, record, recorder)
    _install_session_reads(app, access, record, recorder)


def _install_session_commands(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/sessions")
    async def start_session(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _command_actor(access, record, recorder, request, ticket_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, parsed_ticket_id, command_id, telemetry = parsed
        try:
            payload = SessionStartRequest.model_validate_json(await request.body())
        except ValidationError:
            return _problem_response(_validation_problem())
        command = SessionStartCommand(
            client_command_id=command_id,
            ticket_id=parsed_ticket_id,
            branch_ref=payload.branch_ref,
            crew_name=payload.crew_name,
            harness_ref=payload.harness_ref,
            model_ref=payload.model_ref,
            seat_key=payload.seat_key,
            worktree_ref=payload.worktree_ref,
        )
        outcome = record.work_sessions.start(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return _receipt_response(record, actor, outcome, command_id, telemetry)

    @app.post("/v1/tickets/{ticket_id}/sessions/{session_id}/facts")
    async def record_session_fact(
        ticket_id: str, session_id: str, request: Request
    ) -> JSONResponse:
        parsed = await _command_actor(access, record, recorder, request, ticket_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, parsed_ticket_id, command_id, telemetry = parsed
        try:
            parsed_session_id = _uuid(session_id)
            payload = SessionFactRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        command = _fact_command(command_id, parsed_ticket_id, parsed_session_id, payload.fact)
        outcome = record.work_sessions.record_fact(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return _receipt_response(record, actor, outcome, command_id, telemetry)


def _install_session_reads(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/tickets/{ticket_id}/sessions")
    def list_ticket_sessions(
        ticket_id: str, request: Request, project_key: str | None = None
    ) -> JSONResponse:
        actor = _read_actor(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            context = _telemetry(request)
            parsed_project_key = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        parsed_ticket_id = _ticket_uuid(record, actor, ticket_id, telemetry=context)
        if isinstance(parsed_ticket_id, RecordProblem):
            return _problem_response(parsed_ticket_id)
        telemetry = context.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(parsed_ticket_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = record.work_sessions.for_ticket(
            actor, parsed_ticket_id, parsed_project_key, telemetry=telemetry
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        return _read_response(outcome, HttpTicketSessionList)

    @app.get("/v1/projects/{project_key}/sessions")
    def list_project_sessions(
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
        outcome = record.work_sessions.for_project(
            actor, parsed_project_key, cursor=cursor, limit=limit, telemetry=telemetry
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        return _read_response(outcome, HttpProjectSessionPage)


def _receipt_response(
    record: Record,
    actor: Actor,
    outcome: SessionReceipt | RecordProblem,
    command_id: UUID,
    telemetry: TelemetryContext,
) -> JSONResponse:
    """Return every session command through the one durability-aware mutation boundary."""

    return _mutation_response(
        record,
        outcome,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command_id,
        telemetry=telemetry,
        boundary_model=HttpSessionReceipt,
        accepted_status=200,
    )


def _fact_command(
    command_id: UUID,
    ticket_id: UUID,
    session_id: UUID,
    fact: SessionTransitionFact | SessionCloseFact,
) -> SessionFactCommand:
    """Rebind the wire fact onto the kernel's own authored session vocabulary."""

    if isinstance(fact, SessionCloseFact):
        return SessionCloseCommand(
            client_command_id=command_id,
            ticket_id=ticket_id,
            session_id=session_id,
            evidence_ref=fact.evidence_ref,
            input_tokens=fact.input_tokens,
            outcome=SessionOutcome(fact.outcome.value),
            output_tokens=fact.output_tokens,
        )
    return SessionTransitionCommand(
        client_command_id=command_id,
        ticket_id=ticket_id,
        session_id=session_id,
        reason=fact.reason,
        to_state=SessionState(fact.to_state.value),
    )


async def _command_actor(
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
    request: Request,
    ticket_id: str,
) -> tuple[Actor, UUID, UUID, TelemetryContext] | JSONResponse:
    actor = _authenticate(
        access,
        recorder,
        request,
        required_scope=CredentialScope.TRANSITION,
    )
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        context = _telemetry(request)
    except ValueError:
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
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, parsed_ticket_id, command_id, telemetry


def _read_actor(
    access: Access, recorder: TelemetryRecorder, request: Request
) -> Actor | RecordProblem:
    return _authenticate(
        access,
        recorder,
        request,
        required_scope=_UnscopedAuthentication.ALLOWED,
    )


def _read_response(
    outcome: TicketSessionList | ProjectSessionPage,
    boundary_model: type[HttpTicketSessionList | HttpProjectSessionPage],
) -> JSONResponse:
    boundary = boundary_model.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(status_code=200, content=boundary.model_dump(mode="json"))


def _project_key(value: str | None) -> str:
    if value is None or _PROJECT_KEY.fullmatch(value) is None:
        raise ValueError("invalid project key")
    return value


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()
