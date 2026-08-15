"""Operator-only HTTP adapter for signed external-estate import batches."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import (
    UnscopedAuthentication,
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api.estate_import_port import EstateImportPort
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

__all__ = ["install_estate_import_routes"]

_MAX_BODY_BYTES = 16 * 1024 * 1024


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
) -> Callable[[Request], Awaitable[JSONResponse]]:
    async def import_batch(request: Request) -> JSONResponse:
        actor = _operator_actor(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        parsed = await _parse_request(request, actor, model)
        if isinstance(parsed, JSONResponse):
            return parsed
        command_id, manifest, rows, telemetry, batch_index = parsed
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        result = estate_imports.import_batch(
            actor,
            tier=tier,
            batch_index=batch_index,
            command_id=command_id,
            manifest=manifest,
            rows=rows,
            now=datetime.now(UTC),
            telemetry=telemetry,
        )
        return _result_response(result)

    return import_batch


def _operator_actor(
    access: Access, recorder: TelemetryRecorder, request: Request
) -> Actor | RecordProblem:
    actor = authenticate(access, recorder, request, required_scope=UnscopedAuthentication.ALLOWED)
    if isinstance(actor, RecordProblem) or actor.kind is PrincipalKind.OPERATOR:
        return actor
    return RecordProblem(
        "estate-import-operator-required",
        "Estate imports require operator authority.",
        403,
        "Estate import refused",
    )


async def _parse_request(
    request: Request, actor: Actor, model: type[BaseModel]
) -> (
    tuple[UUID, Mapping[str, object], Sequence[Mapping[str, object]], TelemetryContext, int]
    | JSONResponse
):
    try:
        command_id = uuid_value(request.headers.get("Idempotency-Key"))
        body = await request.body()
        if len(body) > _MAX_BODY_BYTES:
            return problem_response(validation_problem())
        model.model_validate_json(body)
        payload_data = json.loads(body)
        if not isinstance(payload_data, dict):
            return problem_response(validation_problem())
        telemetry = telemetry_context(request).bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        manifest = payload_data["manifest"]
        rows = payload_data["rows"]
        batch_index = payload_data["batch_index"]
        if (
            not isinstance(manifest, Mapping)
            or not isinstance(rows, Sequence)
            or not isinstance(batch_index, int)
        ):
            return problem_response(validation_problem())
        return (
            command_id,
            manifest,
            cast(Sequence[Mapping[str, object]], rows),
            telemetry,
            batch_index,
        )
    except (KeyError, TypeError, ValidationError, ValueError):
        return problem_response(validation_problem())


def _result_response(result: object) -> JSONResponse:
    if isinstance(result, RecordProblem):
        return problem_response(result)
    result_object: Any = result
    result_data: Mapping[str, object]
    if isinstance(result, EstateImportResult):
        result_data = result.model_dump(mode="json", by_alias=True)
    elif hasattr(result_object, "response_payload"):
        result_data = result_object.response_payload()
    elif hasattr(result_object, "model_dump"):
        result_data = result_object.model_dump(mode="json", by_alias=True)
    else:
        result_data = cast(Mapping[str, object], result)
    boundary = EstateImportResult.model_validate_json(encoded(result_data))
    return JSONResponse(
        content=boundary.model_dump(mode="json", by_alias=True),
        status_code=202 if boundary.durability_state.value == "durability_pending" else 201,
    )
