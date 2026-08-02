"""Strict HTTP adapters for project-seat credential issuance and revocation."""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import SeatCredentialIssueRequest, SeatCredentialRevocationRequest
from ctower_client.models import SeatCredentialReceipt as HttpSeatCredentialReceipt
from ctower_kernel.access import Access
from ctower_kernel.record import (
    Actor,
    Record,
    RecordProblem,
)
from ctower_kernel.record.credentials import (
    CredentialScope,
    SeatCredentialIssue,
    SeatCredentialReceipt,
    SeatCredentialRevocation,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def install_credential_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install operator issuance and immediate revocation commands."""

    _install_issue(app, access, record, recorder)
    _install_revoke(app, access, record, recorder)


def _install_issue(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/admin/seat-credentials", status_code=201)
    async def issue(request: Request) -> JSONResponse:
        parsed = await _issue_request(access, recorder, request)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, command, telemetry = parsed
        outcome = access.issue_seat_credential(actor, command, telemetry=telemetry)
        return _response(
            record,
            outcome,
            actor,
            command.client_command_id,
            telemetry=telemetry,
            accepted_status=201,
        )


def _install_revoke(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/admin/seat-credentials/{credential_id}/revocation")
    async def revoke(credential_id: str, request: Request) -> JSONResponse:
        parsed = await _revocation_request(access, recorder, request, credential_id)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, command, telemetry = parsed
        outcome = access.revoke_seat_credential(actor, command, telemetry=telemetry)
        return _response(
            record,
            outcome,
            actor,
            command.client_command_id,
            telemetry=telemetry,
            accepted_status=200,
        )


async def _issue_request(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
) -> tuple[Actor, SeatCredentialIssue, TelemetryContext] | JSONResponse:
    actor = authenticate(
        access,
        recorder,
        request,
        required_scope=UnscopedAuthentication.ALLOWED,
    )
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    try:
        command_id = uuid_value(request.headers.get("Idempotency-Key"))
        payload = SeatCredentialIssueRequest.model_validate_json(await request.body())
        telemetry = telemetry_context(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        command = SeatCredentialIssue(
            client_command_id=command_id,
            credential_digest=bytes.fromhex(payload.credential_digest.removeprefix("sha256:")),
            credential_ref=payload.credential_ref,
            display_name=payload.display_name,
            project_key=payload.project_key,
            scopes=tuple(CredentialScope(scope.value) for scope in payload.scopes),
            seat_key=payload.seat_key,
        )
    except (ValidationError, ValueError):
        return problem_response(validation_problem())
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, command, telemetry


async def _revocation_request(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
    credential_id: str,
) -> tuple[Actor, SeatCredentialRevocation, TelemetryContext] | JSONResponse:
    actor = authenticate(
        access,
        recorder,
        request,
        required_scope=UnscopedAuthentication.ALLOWED,
    )
    if isinstance(actor, RecordProblem):
        return problem_response(actor)
    try:
        command_id = uuid_value(request.headers.get("Idempotency-Key"))
        parsed_credential_id = uuid_value(credential_id)
        payload = SeatCredentialRevocationRequest.model_validate_json(await request.body())
        telemetry = telemetry_context(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        command = SeatCredentialRevocation(
            client_command_id=command_id,
            credential_id=parsed_credential_id,
            reason=payload.reason,
        )
    except (ValidationError, ValueError):
        return problem_response(validation_problem())
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, command, telemetry


def _response(
    record: Record,
    outcome: SeatCredentialReceipt | RecordProblem,
    actor: Actor,
    command_id: UUID,
    *,
    telemetry: TelemetryContext,
    accepted_status: int,
) -> JSONResponse:
    return mutation_response(
        record,
        outcome,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command_id,
        telemetry=telemetry,
        boundary_model=HttpSeatCredentialReceipt,
        accepted_status=accepted_status,
    )
