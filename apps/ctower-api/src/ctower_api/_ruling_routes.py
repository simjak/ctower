"""Strict HTTP adapter for the append-only Agreements ledger."""

from __future__ import annotations

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
from ctower_client.models import RulingAppendRequest, RulingAppendResult, RulingList, RulingRow
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.rulings import RulingAppend, Rulings

__all__: tuple[str, ...] = ()

_BODY_LIMIT = 128 * 1024


class _RulingRoutes:
    def __init__(
        self,
        access: Access,
        record: Record,
        rulings: Rulings,
        recorder: TelemetryRecorder,
    ) -> None:
        self._access = access
        self._record = record
        self._rulings = rulings
        self._recorder = recorder

    async def append(self, request: Request) -> JSONResponse:
        actor = authenticate(
            self._access, self._recorder, request, required_scope=CredentialScope.TRANSITION
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            body = await _bounded_body(request)
            payload = RulingAppendRequest.model_validate_json(body)
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        self._recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = self._rulings.append(
            actor,
            RulingAppend(command_id, payload.verbatim, payload.supersedes_ruling_id),
            telemetry=telemetry,
        )
        return mutation_response(
            self._record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=RulingAppendResult,
            accepted_status=201,
        )

    async def list(self, request: Request, project_key: str | None = None) -> JSONResponse:
        authenticated = self._read_actor(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        actor, telemetry = authenticated
        outcome = self._rulings.list(actor, project_key=project_key, telemetry=telemetry)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = RulingList.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    async def get(self, request: Request, ruling_id: str) -> JSONResponse:
        authenticated = self._read_actor(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        actor, telemetry = authenticated
        try:
            identity = uuid_value(ruling_id)
        except ValueError:
            return problem_response(validation_problem())
        outcome = self._rulings.get(actor, identity, telemetry=telemetry)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        boundary = RulingRow.model_validate_json(encoded(outcome.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    def _read_actor(self, request: Request) -> tuple[Actor, TelemetryContext] | JSONResponse:
        actor = authenticate(
            self._access,
            self._recorder,
            request,
            required_scope=UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id), actor_id=str(actor.principal_id)
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        return actor, telemetry


async def _bounded_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > _BODY_LIMIT:
        raise ValueError("request body exceeds bounded envelope")
    return body


def install_ruling_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    rulings: Rulings,
    recorder: TelemetryRecorder,
) -> None:
    routes = _RulingRoutes(access, record, rulings, recorder)
    app.add_api_route("/v1/rulings", routes.append, methods=["POST"], status_code=201)
    app.add_api_route("/v1/rulings", routes.list, methods=["GET"])
    app.add_api_route("/v1/rulings/{ruling_id}", routes.get, methods=["GET"])
