"""Authenticated HTTP adapters for the Attention findings feed (INV-67)."""

from __future__ import annotations

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
from ctower_client.models import AppendFindingRequest, FindingDispositionRequest
from ctower_client.models import AttentionFindingResult as HttpAttentionFindingResult
from ctower_client.models import FindingDispositionResult as HttpFindingDispositionResult
from ctower_kernel.access import Access
from ctower_kernel.attention import (
    AppendFinding,
    Attention,
    FindingDisposition,
    FindingDispositionOutcome,
)
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope

__all__: tuple[str, ...] = ()


def install_attention_finding_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    attention: Attention,
    recorder: TelemetryRecorder,
) -> None:
    """Install the authenticated append-finding and record-disposition commands."""

    _install_append_finding_route(app, access, record, attention, recorder)
    _install_finding_disposition_route(app, access, record, attention, recorder)


def _install_append_finding_route(
    app: FastAPI,
    access: Access,
    record: Record,
    attention: Attention,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/attention/findings", status_code=202)
    async def append_finding(request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = AppendFindingRequest.model_validate_json(await request.body())
            command = AppendFinding(
                client_command_id=command_id,
                subject_ticket_id=payload.subject_ticket_id,
                kind_key=payload.kind_key,
                reason_code=payload.reason_code,
                effective_owner=payload.effective_owner,
                recommendation=payload.recommendation,
                alternatives=tuple(payload.alternatives),
                consequence=payload.consequence,
                deadline=payload.deadline,
                dedupe_key=payload.dedupe_key,
                source_facts=tuple(payload.source_facts),
            )
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = attention.append_finding(actor, command)
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command.client_command_id,
            telemetry=telemetry,
            boundary_model=HttpAttentionFindingResult,
            accepted_status=202,
        )


def _install_finding_disposition_route(
    app: FastAPI,
    access: Access,
    record: Record,
    attention: Attention,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/attention/findings/{finding_id}/disposition", status_code=202)
    async def record_finding_disposition(finding_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request, required_scope=CredentialScope.CAPTURE)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_finding_id = _uuid(finding_id)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = FindingDispositionRequest.model_validate_json(await request.body())
            command = FindingDisposition(
                client_command_id=command_id,
                finding_id=parsed_finding_id,
                outcome=FindingDispositionOutcome(payload.outcome),
                reason=payload.reason,
            )
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _telemetry(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = attention.record_finding_disposition(actor, command)
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command.client_command_id,
            telemetry=telemetry,
            boundary_model=HttpFindingDispositionResult,
            accepted_status=202,
        )
