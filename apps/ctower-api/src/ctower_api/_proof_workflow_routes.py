"""HTTP adapters for the Proof and Workflow Module Interfaces."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import (
    authenticate as _authenticate,
)
from ctower_api._http_support import (
    problem_response as _problem_response,
)
from ctower_api._http_support import (
    telemetry_context as _telemetry,
)
from ctower_api._http_support import (
    uuid_value as _uuid,
)
from ctower_api._http_support import (
    validation_problem as _validation_problem,
)
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    EvidenceRequest,
    FreezeCriteriaRequest,
    ResolveCloseRequest,
    VerdictRequest,
    WorkflowTransitionRequest,
)
from ctower_client.models import (
    ProofReceipt as HttpProofReceipt,
)
from ctower_client.models import (
    WorkflowReceipt as HttpWorkflowReceipt,
)
from ctower_kernel.access import Access
from ctower_kernel.proof import (
    Criterion,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofMutation,
    ProofReceipt,
    RecordEvidence,
    RecordVerdict,
    VerdictDecision,
)
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow import (
    ResolveClose,
    Workflow,
    WorkflowActor,
    WorkflowMutation,
    WorkflowReceipt,
)

__all__: tuple[str, ...] = ()


def install_proof_workflow_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    proof: Proof,
    workflow: Workflow,
    recorder: TelemetryRecorder,
) -> None:
    """Install the minimum generated-client path for the four-stage fixture."""

    _install_freeze_route(app, access, record, proof, recorder)
    _install_evidence_route(app, access, record, proof, recorder)
    _install_verdict_route(app, access, record, proof, recorder)
    _install_transition_route(app, access, record, workflow, recorder)
    _install_close_route(app, access, record, workflow, recorder)


def _install_freeze_route(
    app: FastAPI, access: Access, record: Record, proof: Proof, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/proof/criteria")
    async def freeze_criteria(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, FreezeCriteriaRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        criteria = tuple(
            Criterion(item.key, item.description, item.candidate_dependent, item.requires_verdict)
            for item in payload.criteria
        )
        return _proof_response(
            record,
            proof.execute(
                _proof_actor(actor),
                ProofMutation(
                    command_id,
                    ticket,
                    payload.expected_version,
                    FreezeCriteria(payload.candidate_digest, actor.principal_id, criteria),
                ),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_evidence_route(
    app: FastAPI, access: Access, record: Record, proof: Proof, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/proof/evidence")
    async def record_evidence(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, EvidenceRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        command = RecordEvidence(
            payload.evidence_id,
            payload.criterion_key,
            payload.candidate_digest,
            payload.artifact_digest,
            payload.content.encode(),
        )
        return _proof_response(
            record,
            proof.execute(
                _proof_actor(actor),
                ProofMutation(command_id, ticket, payload.expected_version, command),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_verdict_route(
    app: FastAPI, access: Access, record: Record, proof: Proof, recorder: TelemetryRecorder
) -> None:
    @app.post("/v1/tickets/{ticket_id}/proof/verdict")
    async def record_verdict(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, VerdictRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        command = RecordVerdict(
            payload.verdict_id,
            payload.criterion_key,
            payload.candidate_digest,
            VerdictDecision(payload.decision.value),
        )
        return _proof_response(
            record,
            proof.execute(
                _proof_actor(actor),
                ProofMutation(command_id, ticket, payload.expected_version, command),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_transition_route(
    app: FastAPI,
    access: Access,
    record: Record,
    workflow: Workflow,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/workflow/transition")
    async def transition(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, WorkflowTransitionRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        return _workflow_response(
            record,
            workflow.advance(
                WorkflowActor(actor.principal_id, actor.tenant_id),
                WorkflowMutation(
                    command_id,
                    ticket,
                    payload.workflow_ref,
                    payload.expected_version,
                    payload.source_stage,
                    payload.destination_stage,
                ),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


def _install_close_route(
    app: FastAPI,
    access: Access,
    record: Record,
    workflow: Workflow,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/tickets/{ticket_id}/workflow/resolve-close")
    async def resolve_close(ticket_id: str, request: Request) -> JSONResponse:
        parsed = await _parse(access, recorder, request, ticket_id, ResolveCloseRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, ticket, command_id, payload, telemetry = parsed
        return _workflow_response(
            record,
            workflow.resolve_close(
                WorkflowActor(actor.principal_id, actor.tenant_id),
                ResolveClose(command_id, ticket, payload.workflow_ref, payload.expected_version),
                telemetry=telemetry,
            ),
            actor,
            command_id,
            telemetry,
        )


async def _parse[Payload: BaseModel](
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
    ticket_id: str,
    model: type[Payload],
) -> tuple[Actor, UUID, UUID, Payload, TelemetryContext] | JSONResponse:
    actor = _authenticate(access, recorder, request)
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
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, ticket, command_id, payload, telemetry


def _proof_actor(actor: Actor) -> ProofActor:
    kind: Literal["operator", "commander"] = (
        "operator" if actor.kind is PrincipalKind.OPERATOR else "commander"
    )
    return ProofActor(actor.principal_id, actor.tenant_id, kind)


def _proof_response(
    record: Record,
    outcome: ProofReceipt | RecordProblem,
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
        boundary_model=HttpProofReceipt,
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
