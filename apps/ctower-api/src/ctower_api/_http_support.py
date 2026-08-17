"""Shared strict HTTP parsing, authentication, and response boundaries."""

from __future__ import annotations

import json
import re
import secrets
from enum import StrEnum
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import Problem
from ctower_client.models import TelemetryContext as HttpTelemetryContext
from ctower_kernel.access import Access
from ctower_kernel.catalog import CatalogProblem
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


class UnscopedAuthentication(StrEnum):
    """One explicit opt-out for authenticated routes without a credential capability."""

    ALLOWED = "allowed"


def authenticate(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
    *,
    required_scope: CredentialScope | UnscopedAuthentication,
) -> Actor | RecordProblem:
    """Resolve one credential and emit a denial without trusting request context."""

    outcome = access.authenticate(request.headers.get("Authorization"))
    if isinstance(outcome, RecordProblem):
        emit_auth_denial(recorder, "access.authenticate", outcome)
        return outcome
    if required_scope is UnscopedAuthentication.ALLOWED:
        return outcome
    refusal = access.authorize_scope(outcome, required_scope)
    if refusal is not None:
        emit_auth_denial(recorder, "access.authorize_scope", refusal)
        return refusal
    return outcome


def emit_auth_denial(recorder: TelemetryRecorder, name: str, problem: RecordProblem) -> None:
    """Emit an authentication denial without accepting caller telemetry."""

    recorder.emit(name, _denial_telemetry(), outcome="error", reason=problem.code)


def problem_response(problem: RecordProblem | CatalogProblem) -> JSONResponse:
    """Validate one kernel refusal through the generated RFC 9457 boundary."""

    boundary = Problem.model_validate_json(encoded(problem.response_payload()))
    return JSONResponse(
        status_code=problem.status,
        content=boundary.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )


def encoded(payload: object) -> str:
    """Encode one stable public response payload."""

    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def uuid_value(value: str | None) -> UUID:
    """Parse a required transport UUID."""

    if value is None:
        raise ValueError("UUID transport value is missing")
    return UUID(value)


def ticket_reference(value: str | None) -> UUID | str:
    """Parse a canonical UUID or a server-assigned PREFIX-N ticket reference."""

    if value is None:
        raise ValueError("ticket reference is missing")
    try:
        return UUID(value)
    except ValueError:
        if re.fullmatch(r"[A-Z]{2,5}-[1-9][0-9]*", value):
            return value
    raise ValueError("ticket reference is outside the authored contract")


def ticket_uuid(
    record: Record,
    actor: Actor,
    value: str | None,
    *,
    telemetry: TelemetryContext,
) -> UUID | RecordProblem:
    """Accept either authored ticket reference form and return the canonical UUID.

    Every ticket-scoped operation resolves through here, so a display key addresses the
    same work a UUID does, and an unresolvable one refuses exactly like an unknown UUID.
    """

    try:
        reference = ticket_reference(value)
    except ValueError:
        return validation_problem()
    if isinstance(reference, UUID):
        return reference
    return record.tickets.resolve_display_key(actor, reference, telemetry=telemetry)


def validation_problem() -> RecordProblem:
    """Return the single strict transport validation refusal."""

    return RecordProblem(
        code="validation-error",
        detail="The request body or transport identifier does not match the authored contract.",
        status=422,
        title="Request validation failed",
    )


def telemetry_context(request: Request) -> TelemetryContext:
    """Validate and translate the generated telemetry boundary."""

    payload = request.headers.get("X-Ctower-Telemetry-Context")
    if payload is None:
        raise ValueError("telemetry context is missing")
    context = HttpTelemetryContext.model_validate_json(payload)
    return TelemetryContext(
        schema=context.schema_id,
        trace_id=context.trace_id,
        span_id=context.span_id,
        trace_flags=context.trace_flags,
        trace_state=context.trace_state,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        command_id=context.command_id,
        ticket_id=context.ticket_id,
        workflow_run_id=context.workflow_run_id,
        stage_attempt_id=context.stage_attempt_id,
        job_id=context.job_id,
        runner_id=context.runner_id,
        fencing_token=context.fencing_token,
        effect_id=context.effect_id,
        component_revision_id=context.component_revision_id,
        deployment_id=context.deployment_id,
    )


def _denial_telemetry() -> TelemetryContext:
    correlation_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=secrets.token_hex(16),
        span_id=secrets.token_hex(8),
        trace_flags=0,
        correlation_id=correlation_id,
        causation_id=correlation_id,
        tenant_id="unauthenticated",
        actor_id="unauthenticated",
        command_id=correlation_id,
    )
