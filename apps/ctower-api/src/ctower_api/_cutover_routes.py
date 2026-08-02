"""Restricted I1.7B migration commands and read-only cutover projections."""

from __future__ import annotations

import re
from typing import cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import emit_auth_denial as _emit_auth_denial
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._migration_port import MigrationPort
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectEpochRefusalRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
    CtowerProjectMigrationReceipt,
    CtowerProjectReconciliationResult,
)
from ctower_client.models import (
    CtowerProjectCutoverHealth as HttpCutoverHealth,
)
from ctower_client.models import (
    ProjectDeliveryView as HttpProjectDeliveryView,
)
from ctower_kernel.access import Access
from ctower_kernel.projections import Projections
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_IMPORT_BODY_LIMIT = 262_144
_FENCE_BODY_LIMIT = 65_536
_OPERATOR_BODY_LIMIT = 8_388_608


def install_cutover_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    projections: Projections | None,
    migration: MigrationPort | None,
    recorder: TelemetryRecorder,
) -> None:
    """Install only composed Interfaces; I1.7C epoch mutations always refuse."""

    if migration is not None:
        _install_migration_routes(app, access, record, migration, recorder)
    _install_epoch_refusals(app, access, recorder)
    if projections is not None:
        _install_read_routes(app, access, projections, recorder)


def _install_migration_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    _install_binding_routes(app, access, record, migration, recorder)
    _install_import_route(app, access, record, migration, recorder)
    _install_run_routes(app, access, record, migration, recorder)
    _install_fence_route(app, access, record, migration, recorder)


def _install_binding_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    _install_inventory_route(app, access, record, migration, recorder)
    _install_export_route(app, access, record, migration, recorder)
    _install_plan_route(app, access, record, migration, recorder)


def _install_inventory_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/inventory")
    async def inventory(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectImportRunCreateRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        outcome = migration.create_run(
            actor,
            cast(CtowerProjectImportRunCreateRequest, payload),
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectImportRun,
            accepted_status=201,
        )


def _install_export_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/export")
    async def export(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectExportEqualityBindRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        outcome = migration.bind_export_equality(
            actor,
            cast(CtowerProjectExportEqualityBindRequest, payload),
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectImportRun,
            accepted_status=200,
        )


def _install_plan_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/plan")
    async def plan(request: Request) -> JSONResponse:
        parsed = await _parse_operator(access, recorder, request, CtowerProjectAliasPlanBindRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        outcome = migration.bind_alias_plan(
            actor,
            cast(CtowerProjectAliasPlanBindRequest, payload),
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectImportRun,
            accepted_status=200,
        )


def _install_import_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/import")
    async def import_records(request: Request) -> JSONResponse:
        actor = access.authenticate_importer_credential(request.headers.get("Authorization"))
        if isinstance(actor, RecordProblem):
            _emit_auth_denial(recorder, "access.authenticate_importer", actor)
            return _problem_response(actor)
        try:
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = CtowerProjectImportBatchRequest.model_validate_json(
                await _bounded_body(request, _IMPORT_BODY_LIMIT)
            )
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _actor_telemetry(request, actor, command_id)
        recorder.emit("access.authenticate_importer", telemetry, outcome="ok", reason="authorized")
        outcome = migration.apply_batch(
            actor,
            payload,
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectImportBatchResult,
            accepted_status=200,
        )


def _install_run_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    _install_reconcile_route(app, access, record, migration, recorder)
    _install_run_read_route(app, access, migration, recorder)
    _install_correction_route(app, access, record, migration, recorder)


def _install_reconcile_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/reconcile")
    async def reconcile(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectImportFinalizeRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        outcome = migration.finalize_run(
            actor,
            cast(CtowerProjectImportFinalizeRequest, payload),
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectReconciliationResult,
            accepted_status=200,
        )


def _install_run_read_route(
    app: FastAPI,
    access: Access,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/migrations/ctower-project/import-runs/{run_id}")
    def get_run(run_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(
            access,
            recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_run_id = _uuid(run_id)
            telemetry = _actor_telemetry(request, actor)
        except ValueError:
            return _problem_response(_validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _response(migration.get_run(actor, parsed_run_id))


def _install_correction_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/corrections")
    async def append_correction(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectImportCorrectionRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        outcome = migration.append_correction(
            actor,
            cast(CtowerProjectImportCorrectionRequest, payload),
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectMigrationReceipt,
            accepted_status=201,
        )


def _install_fence_route(
    app: FastAPI,
    access: Access,
    record: Record,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/fence-observations")
    async def report_fence(request: Request) -> JSONResponse:
        actor = access.authenticate_fence_observer(request.headers.get("Authorization"))
        if isinstance(actor, RecordProblem):
            _emit_auth_denial(recorder, "access.authenticate_fence_observer", actor)
            return _problem_response(actor)
        try:
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = CtowerProjectFenceObservationRequest.model_validate_json(
                await _bounded_body(request, _FENCE_BODY_LIMIT)
            )
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        telemetry = _actor_telemetry(request, actor, command_id)
        recorder.emit(
            "access.authenticate_fence_observer",
            telemetry,
            outcome="ok",
            reason="authorized",
        )
        outcome = migration.report_fence_observation(
            actor,
            payload,
            command_id=command_id,
            telemetry=telemetry,
        )
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=CtowerProjectMigrationReceipt,
            accepted_status=201,
        )


def _install_epoch_refusals(
    app: FastAPI,
    access: Access,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/prepare")
    async def prepare(request: Request) -> JSONResponse:
        return await _refuse_epoch(request, access, recorder)

    @app.post("/v1/migrations/ctower-project/commit-development-epoch")
    async def commit_development_epoch(request: Request) -> JSONResponse:
        return await _refuse_epoch(request, access, recorder)


async def _refuse_epoch(
    request: Request,
    access: Access,
    recorder: TelemetryRecorder,
) -> JSONResponse:
    parsed = await _parse_operator(access, recorder, request, CtowerProjectEpochRefusalRequest)
    if isinstance(parsed, JSONResponse):
        return parsed
    _, _, command_id, _ = parsed
    return _problem_response(
        RecordProblem(
            code="i1-7c-required",
            detail=(
                "Live cutover preparation and epoch commitment require independent I1.7C review."
            ),
            status=409,
            title="ctower-project epoch mutation deferred",
            command_id=command_id,
        )
    )


async def _parse_operator(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
    model: type[BaseModel],
) -> tuple[Actor, BaseModel, UUID, TelemetryContext] | JSONResponse:
    actor = _authenticate(
        access,
        recorder,
        request,
        required_scope=_UnscopedAuthentication.ALLOWED,
    )
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        payload = model.model_validate_json(await _bounded_body(request, _OPERATOR_BODY_LIMIT))
        telemetry = _actor_telemetry(request, actor, command_id)
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
    return actor, payload, command_id, telemetry


def _actor_telemetry(
    request: Request,
    actor: Actor,
    command_id: UUID | None = None,
) -> TelemetryContext:
    values = {
        "tenant_id": str(actor.tenant_id),
        "actor_id": str(actor.principal_id),
    }
    if command_id is not None:
        values["command_id"] = str(command_id)
    return _telemetry(request).bind(**values)


async def _bounded_body(request: Request, limit: int) -> bytes:
    length = request.headers.get("Content-Length")
    if length is not None and (not length.isdigit() or int(length) > limit):
        raise ValueError("request body exceeds the operation limit")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ValueError("request body exceeds the operation limit")
    return bytes(body)


def _response(outcome: BaseModel | RecordProblem) -> JSONResponse:
    if isinstance(outcome, RecordProblem):
        return _problem_response(outcome)
    return JSONResponse(content=outcome.model_dump(mode="json", by_alias=True))


def _install_read_routes(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/migrations/ctower-project/cutover-health")
    def get_cutover_health(request: Request) -> JSONResponse:
        actor = _authenticate(
            access,
            recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        boundary = HttpCutoverHealth.model_validate_json(
            _encoded(projections.cutover_health(actor).response_payload())
        )
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    @app.get("/v1/projects/{project_key}/delivery")
    def get_project_delivery(project_key: str, request: Request) -> JSONResponse:
        actor = _authenticate(
            access,
            recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        if _PROJECT_KEY.fullmatch(project_key) is None:
            return _problem_response(_validation_problem())
        view = projections.project_delivery(actor, project_key)
        if view is None:
            return _problem_response(
                RecordProblem(
                    code="project-delivery-unavailable",
                    detail="No authorized Project Delivery rows exist for this project.",
                    status=404,
                    title="Project Delivery unavailable",
                )
            )
        boundary = HttpProjectDeliveryView.model_validate_json(_encoded(view.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))
