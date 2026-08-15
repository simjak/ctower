"""Operator-only HTTP adapter for signed external-estate import batches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    EstateCompanyRecordsImportRequest,
    EstateImportResult,
    EstateInboxImportRequest,
    EstateKnowledgeImportRequest,
    EstateRulingsImportRequest,
)
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.interface import Record
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["EstateImportPort", "install_estate_import_routes"]

_MAX_BODY_BYTES = 16 * 1024 * 1024


class EstateImportPort(Protocol):
    """Small application-to-kernel port for one operator estate batch."""

    def import_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportResult | RecordProblem: ...


def install_estate_import_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    estate_imports: EstateImportPort,
    recorder: TelemetryRecorder,
) -> None:
    """Install the four generated operator-authority import operations."""

    del record
    routes = (
        ("/v1/migrations/estate/inbox", "inbox_history", EstateInboxImportRequest),
        ("/v1/migrations/estate/rulings", "agreed_decisions", EstateRulingsImportRequest),
        ("/v1/migrations/estate/knowledge", "knowledge_documents", EstateKnowledgeImportRequest),
        (
            "/v1/migrations/estate/company-records",
            "company_records",
            EstateCompanyRecordsImportRequest,
        ),
    )
    for path, tier, model in routes:
        app.add_api_route(
            path,
            _handler(access, estate_imports, recorder, tier, model),
            methods=["POST"],
            status_code=201,
            name=f"import_estate_{tier}",
        )


def _handler(
    access: Access,
    estate_imports: EstateImportPort,
    recorder: TelemetryRecorder,
    tier: str,
    model: type[BaseModel],
):
    async def import_batch(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        if actor.kind is not PrincipalKind.OPERATOR:
            return problem_response(
                RecordProblem(
                    "estate-import-operator-required",
                    "Estate imports require operator authority.",
                    403,
                    "Estate import refused",
                )
            )
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            body = await request.body()
            if len(body) > _MAX_BODY_BYTES:
                return problem_response(validation_problem())
            payload = model.model_validate_json(body)
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        result = estate_imports.import_batch(
            actor,
            tier=tier,
            command_id=command_id,
            manifest=cast(Mapping[str, object], payload.model_dump(mode="json", by_alias=True)["manifest"]),
            rows=cast(Sequence[Mapping[str, object]], payload.model_dump(mode="json", by_alias=True)["rows"]),
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        if isinstance(result, RecordProblem):
            return problem_response(result)
        boundary = EstateImportResult.model_validate(result.model_dump(mode="json", by_alias=True))
        return JSONResponse(
            content=boundary.model_dump(mode="json", by_alias=True),
            status_code=202 if boundary.durability_state.value == "durability_pending" else 201,
        )

    return import_batch
