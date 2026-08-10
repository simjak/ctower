"""Protected ticket-custody HTTP command adapter."""

from __future__ import annotations

from uuid import UUID

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
from ctower_client.models import CustodyTransferRequest
from ctower_client.models import TicketCommandResult as HttpTicketCommandResult
from ctower_kernel.access import Access
from ctower_kernel.record import CustodyCommand, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()


def install_custody_route(
    app: FastAPI,
    access: Access,
    record: Record,
    work: Work,
    recorder: TelemetryRecorder,
) -> None:
    """Bind the protected custody command Adapter."""

    @app.post("/v1/tickets/{ticket_id}/custody")
    async def transfer_ticket_custody(ticket_id: str, request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=CredentialScope.TRANSITION)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            parsed_ticket_id = uuid_value(ticket_id)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = CustodyTransferRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(parsed_ticket_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = work.transfer_custody(
            actor,
            _command(command_id, parsed_ticket_id, payload),
            telemetry=telemetry,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpTicketCommandResult,
            accepted_status=200,
        )


def _command(
    command_id: UUID,
    ticket_id: UUID,
    payload: CustodyTransferRequest,
) -> CustodyCommand:
    return CustodyCommand(
        client_command_id=command_id,
        expected_version=payload.expected_version,
        from_custodian_id=payload.from_custodian_id,
        protected_transfer=payload.protected_transfer,
        reason=payload.reason,
        ticket_id=ticket_id,
        to_custodian_id=payload.to_custodian_id,
    )
