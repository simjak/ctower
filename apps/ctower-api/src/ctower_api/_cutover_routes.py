"""Restricted I1.7B migration commands and read-only cutover projections."""

from __future__ import annotations

import re
from typing import cast
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import emit_auth_denial as _emit_auth_denial
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._migration_port import MigrationPort
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectEpochRefusalRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRunCreateRequest,
)
from ctower_client.models import (
    CtowerProjectCutoverHealth as HttpCutoverHealth,
)
from ctower_client.models import (
    ProjectDeliveryView as HttpProjectDeliveryView,
)
from ctower_kernel.access import Access
from ctower_kernel.projections import Projections
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def install_cutover_routes(
    app: FastAPI,
    access: Access,
    projections: Projections | None,
    migration: MigrationPort | None,
    recorder: TelemetryRecorder,
) -> None:
    """Install only composed Interfaces; I1.7C epoch mutations always refuse."""

    if migration is not None:
        _install_migration_routes(app, access, migration, recorder)
    _install_epoch_refusals(app, access, recorder)
    if projections is not None:
        _install_read_routes(app, access, projections, recorder)


def _install_migration_routes(
    app: FastAPI,
    access: Access,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    _install_binding_routes(app, access, migration, recorder)
    _install_import_route(app, access, migration, recorder)
    _install_run_routes(app, access, migration, recorder)
    _install_fence_route(app, access, migration, recorder)


def _install_binding_routes(
    app: FastAPI,
    access: Access,
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
        return _response(
            migration.create_run(
                actor,
                cast(CtowerProjectImportRunCreateRequest, payload),
                command_id=command_id,
                telemetry=telemetry,
            )
        )

    @app.post("/v1/migrations/ctower-project/export")
    async def export(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectExportEqualityBindRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        return _response(
            migration.bind_export_equality(
                actor,
                cast(CtowerProjectExportEqualityBindRequest, payload),
                command_id=command_id,
                telemetry=telemetry,
            )
        )

    @app.post("/v1/migrations/ctower-project/plan")
    async def plan(request: Request) -> JSONResponse:
        parsed = await _parse_operator(access, recorder, request, CtowerProjectAliasPlanBindRequest)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        return _response(
            migration.bind_alias_plan(
                actor,
                cast(CtowerProjectAliasPlanBindRequest, payload),
                command_id=command_id,
                telemetry=telemetry,
            )
        )


def _install_import_route(
    app: FastAPI,
    access: Access,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/import")
    async def import_records(request: Request) -> JSONResponse:
        try:
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = CtowerProjectImportBatchRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        actor = access.authenticate_importer(
            request.headers.get("Authorization"),
            run_id=payload.run_id,
            cutover_id=payload.cutover_id,
            project_key="ctower",
        )
        if isinstance(actor, RecordProblem):
            _emit_auth_denial(recorder, "access.authenticate_importer", actor)
            return _problem_response(actor)
        telemetry = _actor_telemetry(request, actor, command_id)
        recorder.emit("access.authenticate_importer", telemetry, outcome="ok", reason="authorized")
        return _response(migration.apply_batch(actor, payload, telemetry=telemetry))


def _install_run_routes(
    app: FastAPI,
    access: Access,
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
        return _response(
            migration.finalize_run(
                actor,
                cast(CtowerProjectImportFinalizeRequest, payload),
                command_id=command_id,
                telemetry=telemetry,
            )
        )

    @app.get("/v1/migrations/ctower-project/import-runs/{run_id}")
    def get_run(run_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_run_id = _uuid(run_id)
            telemetry = _actor_telemetry(request, actor)
        except ValueError:
            return _problem_response(_validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        return _response(migration.get_run(actor, parsed_run_id))

    @app.post("/v1/migrations/ctower-project/corrections")
    async def append_correction(request: Request) -> JSONResponse:
        parsed = await _parse_operator(
            access, recorder, request, CtowerProjectImportCorrectionRequest
        )
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, payload, command_id, telemetry = parsed
        return _response(
            migration.append_correction(
                actor,
                cast(CtowerProjectImportCorrectionRequest, payload),
                command_id=command_id,
                telemetry=telemetry,
            )
        )


def _install_fence_route(
    app: FastAPI,
    access: Access,
    migration: MigrationPort,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/migrations/ctower-project/fence-observations")
    async def report_fence(request: Request) -> JSONResponse:
        try:
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = CtowerProjectFenceObservationRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        actor = access.authenticate_fence_observer(request.headers.get("Authorization"))
        if isinstance(actor, RecordProblem):
            _emit_auth_denial(recorder, "access.authenticate_fence_observer", actor)
            return _problem_response(actor)
        telemetry = _actor_telemetry(request, actor, command_id)
        recorder.emit(
            "access.authenticate_fence_observer",
            telemetry,
            outcome="ok",
            reason="authorized",
        )
        return _response(
            migration.report_fence_observation(
                actor,
                payload,
                command_id=command_id,
                telemetry=telemetry,
            )
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
    actor = _authenticate(access, recorder, request)
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        payload = model.model_validate_json(await request.body())
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
        actor = _authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        boundary = HttpCutoverHealth.model_validate_json(
            _encoded(projections.cutover_health(actor).response_payload())
        )
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    @app.get("/v1/projects/{project_key}/delivery")
    def get_project_delivery(project_key: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request)
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
