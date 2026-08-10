"""Hidden, epoch-scoped HTTP transport for the one-way Request import."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.request_cutover import (
    RequestBatchProof,
    RequestCutover,
    RequestCutoverComplete,
    RequestCutoverImport,
    RequestCutoverPrepare,
    RequestCutoverResult,
)

__all__: tuple[str, ...] = ()

_BODY_LIMIT = 20 * 1024 * 1024
_Digest = Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
_Artifact = Annotated[str, Field(min_length=2, max_length=16 * 1024 * 1024)]
_PublicKey = Annotated[str, Field(min_length=1, max_length=16 * 1024)]


class _Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _PrepareBody(_Boundary):
    manifest: _Artifact
    fence: _Artifact
    reviewer_public_key_pem: _PublicKey


class _ImportBody(_Boundary):
    manifest_digest: _Digest
    source_request_id: Annotated[str, Field(pattern="^R[1-9][0-9]*$")]
    content: Annotated[str, Field(min_length=1, max_length=65536)]
    fence: _Artifact
    reviewer_public_key_pem: _PublicKey


class _ProofBody(_Boundary):
    proof: _Artifact
    reviewer_public_key_pem: _PublicKey


class _CompleteBody(_Boundary):
    manifest_digest: _Digest
    final_fence: _Artifact
    reviewer_public_key_pem: _PublicKey


class _CutoverResultBoundary(_Boundary):
    accepted_position: Annotated[int, Field(ge=1)] | None
    command_id: UUID
    durability_state: Literal["durability_pending", "accepted"]
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=2)]
    imported_count: Annotated[int, Field(ge=0)]
    manifest_digest: _Digest
    operation: Literal["prepare", "import", "reconcile_batch", "complete"]
    request_id: UUID | None
    request_number: Annotated[int, Field(ge=1)] | None
    state: Literal["prepared", "completed"]
    target_watermark: Annotated[int, Field(ge=1)]


@dataclass(frozen=True, slots=True)
class _Parsed:
    actor: Actor
    command_id: UUID
    telemetry: TelemetryContext


class _RequestCutoverRoutes:
    def __init__(
        self,
        access: Access,
        record: Record,
        cutover: RequestCutover,
        recorder: TelemetryRecorder,
    ) -> None:
        self._access = access
        self._record = record
        self._cutover = cutover
        self._recorder = recorder

    def inventory(self, request: Request) -> JSONResponse:
        actor = self._actor(request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        outcome = self._cutover.authority_inventory(actor)
        return (
            problem_response(outcome)
            if isinstance(outcome, RecordProblem)
            else JSONResponse(outcome)
        )

    async def prepare(self, request: Request) -> JSONResponse:
        parsed, body = await self._mutation(request, _PrepareBody)
        if isinstance(parsed, JSONResponse):
            return parsed
        body = cast(_PrepareBody, body)
        outcome = self._cutover.prepare(
            parsed.actor,
            RequestCutoverPrepare(
                parsed.command_id,
                body.manifest,
                body.fence,
                body.reviewer_public_key_pem,
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, status=202)

    async def import_row(self, request: Request) -> JSONResponse:
        parsed, body = await self._mutation(request, _ImportBody)
        if isinstance(parsed, JSONResponse):
            return parsed
        body = cast(_ImportBody, body)
        outcome = self._cutover.import_row(
            parsed.actor,
            RequestCutoverImport(
                parsed.command_id,
                body.manifest_digest,
                body.source_request_id,
                body.content,
                body.fence,
                body.reviewer_public_key_pem,
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, status=201)

    def reconcile(self, request: Request, manifest_digest: str, batch_index: int) -> JSONResponse:
        actor = self._actor(request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        if batch_index < 0:
            return problem_response(validation_problem())
        outcome = self._cutover.reconcile(actor, manifest_digest, batch_index)
        if isinstance(outcome, RecordProblem):
            return problem_response(outcome)
        return JSONResponse(outcome.response_payload())

    async def record_proof(self, request: Request) -> JSONResponse:
        parsed, body = await self._mutation(request, _ProofBody)
        if isinstance(parsed, JSONResponse):
            return parsed
        body = cast(_ProofBody, body)
        outcome = self._cutover.record_batch_proof(
            parsed.actor,
            RequestBatchProof(
                parsed.command_id,
                body.proof,
                body.reviewer_public_key_pem,
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, status=202)

    async def complete(self, request: Request) -> JSONResponse:
        parsed, body = await self._mutation(request, _CompleteBody)
        if isinstance(parsed, JSONResponse):
            return parsed
        body = cast(_CompleteBody, body)
        outcome = self._cutover.complete(
            parsed.actor,
            RequestCutoverComplete(
                parsed.command_id,
                body.manifest_digest,
                body.final_fence,
                body.reviewer_public_key_pem,
            ),
            telemetry=parsed.telemetry,
        )
        return self._response(parsed, outcome, status=202)

    async def _mutation(
        self, request: Request, model: type[_Boundary]
    ) -> tuple[_Parsed | JSONResponse, _Boundary | None]:
        actor = self._actor(request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor), None
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
            body = await request.body()
            if len(body) > _BODY_LIMIT:
                return problem_response(validation_problem()), None
            payload = model.model_validate_json(body)
        except (ValidationError, ValueError):
            return problem_response(validation_problem()), None
        return _Parsed(actor, command_id, telemetry), payload

    def _actor(self, request: Request) -> Actor | RecordProblem:
        return authenticate(
            self._access,
            self._recorder,
            request,
            required_scope=UnscopedAuthentication.ALLOWED,
        )

    def _response(
        self,
        parsed: _Parsed,
        outcome: RequestCutoverResult | RecordProblem,
        *,
        status: int,
    ) -> JSONResponse:
        return mutation_response(
            self._record,
            outcome,
            tenant_id=parsed.actor.tenant_id,
            principal_id=parsed.actor.principal_id,
            command_id=parsed.command_id,
            telemetry=parsed.telemetry,
            boundary_model=_CutoverResultBoundary,
            accepted_status=status,
        )


def install_request_cutover_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    cutover: RequestCutover,
    recorder: TelemetryRecorder,
) -> None:
    """Install no ordinary-schema operation; the prepared epoch alone makes it usable."""

    routes = _RequestCutoverRoutes(access, record, cutover, recorder)
    prefix = "/_internal/request-cutover"
    app.add_api_route(
        f"{prefix}/authority-inventory",
        routes.inventory,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        f"{prefix}/prepare", routes.prepare, methods=["POST"], include_in_schema=False
    )
    app.add_api_route(
        f"{prefix}/rows", routes.import_row, methods=["POST"], include_in_schema=False
    )
    app.add_api_route(
        f"{prefix}/reconcile/{{manifest_digest}}/{{batch_index}}",
        routes.reconcile,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        f"{prefix}/batch-proofs",
        routes.record_proof,
        methods=["POST"],
        include_in_schema=False,
    )
    app.add_api_route(
        f"{prefix}/complete", routes.complete, methods=["POST"], include_in_schema=False
    )
