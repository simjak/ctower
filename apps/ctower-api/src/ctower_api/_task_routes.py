"""HTTP adapters for explicit Workflow start and authoritative Work commands."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    AdmitIntent,
    AssignmentChangeRequest,
    AssignmentList,
    AuditPage,
    BlockIntent,
    DeferIntent,
    PriorityChangeRequest,
    RelationRequest,
    ReopenIntent,
    TicketIntentRequest,
    UnblockIntent,
    WorkflowStartRequest,
)
from ctower_client.models import WorkflowReceipt as HttpWorkflowReceipt
from ctower_client.models import WorkReceipt as HttpWorkReceipt
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record import AuditPage as KernelAuditPage
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import (
    AddRelation,
    Admit,
    AssignmentKind,
    Block,
    ChangeAssignment,
    ChangePriority,
    Defer,
    RelationKind,
    Reopen,
    Unblock,
    Work,
    WorkCommand,
    WorkReceipt,
)
from ctower_kernel.workflow import Workflow, WorkflowActor, WorkflowReceipt, WorkflowStart

__all__: tuple[str, ...] = ()
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def install_task_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    work: Work,
    workflow: Workflow | None,
    recorder: TelemetryRecorder,
) -> None:
    """Install CP2 operations without a writable status or Board mutation."""

    _install_priority(app, access, record, work, recorder)
    _install_assignment(app, access, record, work, recorder)
    _install_assignment_list(app, access, work, recorder)
    _install_intent(app, access, record, work, recorder)
    _install_relation(app, access, record, work, recorder)
    _install_audit(app, access, record, recorder)
    if workflow is not None:
        _install_start(app, access, record, workflow, recorder)


def _install_start(
    app: FastAPI,
    access: Access,
    record: Record,
    workflow: Workflow,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/workflow/start")
    async def start(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, WorkflowStartRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        outcome = workflow.start(
            WorkflowActor(actor.principal_id, actor.tenant_id),
            WorkflowStart(
                command_id,
                ticket,
                payload.workflow_ref,
                payload.workflow_digest,
                payload.execution_policy_ref,
                payload.execution_policy_digest,
                payload.gate_policy_ref,
                payload.gate_policy_digest,
                payload.evidence_policy_ref,
                payload.evidence_policy_digest,
            ),
            telemetry=telemetry,
        )
        return _workflow_response(record, outcome, actor, command_id, telemetry)


def _install_priority(
    app: FastAPI, access: Access, record: Record, work: Work, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/priority")
    async def priority(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, PriorityChangeRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        return _work_response(
            record,
            work.execute(
                actor,
                ChangePriority(
                    command_id,
                    ticket,
                    payload.expected_version,
                    payload.reason,
                    payload.priority.value,
                    payload.urgent_evidence_ref,
                ),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_assignment(
    app: FastAPI, access: Access, record: Record, work: Work, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/assignments")
    async def assignment(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, AssignmentChangeRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        return _work_response(
            record,
            work.execute(
                actor,
                ChangeAssignment(
                    command_id,
                    ticket,
                    payload.expected_version,
                    payload.reason,
                    AssignmentKind(payload.assignment_kind.value),
                    payload.to_principal_id,
                    payload.scope_ref,
                ),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_assignment_list(
    app: FastAPI, access: Access, work: Work, recorder: TelemetryRecorder
) -> None:
    @app.get("/v1/tickets/{ticket_id}/assignments")
    def assignment_list(
        ticket_id: str, request: Request, project_key: str | None = None
    ) -> JSONResponse:
        parsed = _read_actor(access, recorder, request, ticket_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, _ = parsed
        try:
            project = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        outcome = work.assignments(actor, ticket, project)
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        boundary = AssignmentList.model_validate_json(
            _encoded(
                {
                    "assignments": tuple(item.response_payload() for item in outcome),
                    "ticket_id": str(ticket),
                }
            )
        )
        return JSONResponse(content=boundary.model_dump(mode="json"))


def _install_intent(
    app: FastAPI,
    access: Access,
    record: Record,
    work: Work,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/intents")
    async def intent(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, TicketIntentRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        command = _intent(command_id, ticket, payload)
        return _work_response(
            record,
            work.execute(actor, command, telemetry=telemetry),
            actor,
            command_id,
            telemetry,
        )


def _intent(command_id: UUID, ticket_id: UUID, request: TicketIntentRequest) -> WorkCommand:
    value = request.intent
    common = (command_id, ticket_id, value.expected_version, value.reason)
    if isinstance(value, AdmitIntent):
        return Admit(*common)
    if isinstance(value, DeferIntent):
        return Defer(*common, value.review_after)
    if isinstance(value, BlockIntent):
        return Block(
            *common,
            value.blocker_id,
            value.blocker_kind,
            value.reason_class,
            value.owner_principal_id,
            value.source_ref,
            value.affected_stage,
            value.resolution_condition,
            value.next_check_at,
            value.dependency_ref,
            value.board_impact,
        )
    if isinstance(value, UnblockIntent):
        return Unblock(*common, value.blocker_id, value.resolution_evidence_ref)
    if isinstance(value, ReopenIntent):
        return Reopen(*common, value.priority_policy)
    raise TypeError("unsupported typed intent")


def _install_relation(
    app: FastAPI, access: Access, record: Record, work: Work, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/relations")
    async def relation(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, RelationRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        return _work_response(
            record,
            work.execute(
                actor,
                AddRelation(
                    command_id,
                    ticket,
                    payload.expected_version,
                    payload.reason,
                    RelationKind(payload.relation_kind.value),
                    payload.target_ticket_id,
                ),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_audit(
    app: FastAPI, access: Access, record: Record, recorder: TelemetryRecorder
) -> None:
    @app.get("/v1/tickets/{ticket_id}/audit")
    def audit(
        ticket_id: str,
        request: Request,
        project_key: str | None = None,
        cursor: int = 0,
        limit: int = 50,
    ) -> JSONResponse:
        parsed = _read_actor(access, recorder, request, ticket_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, telemetry = parsed
        try:
            project = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        outcome = record.ticket_audit(
            actor, ticket, project, cursor=cursor, limit=limit, telemetry=telemetry
        )
        return _audit_response(outcome)


def _project_key(value: str | None) -> str:
    if value is None or _PROJECT_KEY.fullmatch(value) is None:
        raise ValueError("invalid project key")
    return value


async def _parse[Payload: BaseModel](
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
    ticket_id: str,
    model: type[Payload],
) -> tuple[Actor, UUID, UUID, Payload, TelemetryContext] | JSONResponse:
    actor = _authenticate(
        access,
        recorder,
        request,
        required_scope=CredentialScope.TRANSITION,
    )
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        ticket = _uuid(ticket_id)
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        payload = model.model_validate_json(await request.body())
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(ticket),
        )
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    return actor, ticket, command_id, payload, telemetry


def _read_actor(
    access: Access, recorder: TelemetryRecorder, request: Request, ticket_id: str
) -> tuple[Actor, UUID, TelemetryContext] | JSONResponse:
    actor = _authenticate(
        access,
        recorder,
        request,
        required_scope=_UnscopedAuthentication.ALLOWED,
    )
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        ticket = _uuid(ticket_id)
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            ticket_id=str(ticket),
        )
    except ValueError:
        return _problem_response(_validation_problem())
    return actor, ticket, telemetry


def _work_response(
    record: Record,
    outcome: WorkReceipt | RecordProblem,
    actor: Actor,
    command_id: UUID,
    telemetry: TelemetryContext,
) -> JSONResponse:
    return _mutation_response(
        record,
        outcome,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command_id,
        telemetry=telemetry,
        boundary_model=HttpWorkReceipt,
        accepted_status=200,
    )


def _workflow_response(
    record: Record,
    outcome: WorkflowReceipt | RecordProblem,
    actor: Actor,
    command_id: UUID,
    telemetry: TelemetryContext,
) -> JSONResponse:
    return _mutation_response(
        record,
        outcome,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command_id,
        telemetry=telemetry,
        boundary_model=HttpWorkflowReceipt,
        accepted_status=200,
    )


def _audit_response(outcome: KernelAuditPage | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    boundary = AuditPage.model_validate_json(_encoded(outcome.response_payload()))
    return JSONResponse(content=boundary.model_dump(mode="json"))
