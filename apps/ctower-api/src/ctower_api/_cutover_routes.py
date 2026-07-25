"""I1.7A read routes and explicit online-only migration refusal stubs."""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    CtowerProjectCutoverHealth as HttpCutoverHealth,
)
from ctower_client.models import (
    CtowerProjectMigrationStubRequest,
)
from ctower_client.models import (
    ProjectDeliveryView as HttpProjectDeliveryView,
)
from ctower_kernel.access import Access
from ctower_kernel.projections import Projections
from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def install_cutover_routes(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    """Install real reads plus phase-specific stubs that cannot mutate or spool."""

    _install_source_phase_stubs(app, access, recorder)
    _install_cutover_phase_stubs(app, access, recorder)
    _install_read_routes(app, access, projections, recorder)


async def _refuse_phase(
    request: Request,
    access: Access,
    recorder: TelemetryRecorder,
    phase: str,
) -> JSONResponse:
    actor = _authenticate(access, recorder, request)
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        CtowerProjectMigrationStubRequest.model_validate_json(await request.body())
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    return _problem_response(
        RecordProblem(
            code="i1-7b-required",
            detail=(
                f"The {phase} phase is an online-only I1.7A stub. "
                "I1.7B/C must implement and independently review it."
            ),
            status=409,
            title="ctower-project migration phase deferred",
            command_id=command_id,
        )
    )


def _install_source_phase_stubs(
    app: FastAPI,
    access: Access,
    recorder: TelemetryRecorder,
) -> None:
    """Install source-read/import spellings as explicit I1.7B refusals."""

    @app.post("/v1/migrations/ctower-project/inventory")
    async def inventory(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "inventory")

    @app.post("/v1/migrations/ctower-project/export")
    async def export(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "export")

    @app.post("/v1/migrations/ctower-project/plan")
    async def plan(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "plan")

    @app.post("/v1/migrations/ctower-project/import")
    async def import_records(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "import")


def _install_cutover_phase_stubs(
    app: FastAPI,
    access: Access,
    recorder: TelemetryRecorder,
) -> None:
    """Install reconcile/cutover spellings as explicit I1.7B/C refusals."""

    @app.post("/v1/migrations/ctower-project/reconcile")
    async def reconcile(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "reconcile")

    @app.post("/v1/migrations/ctower-project/prepare")
    async def prepare(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "prepare")

    @app.post("/v1/migrations/ctower-project/commit-development-epoch")
    async def commit_development_epoch(request: Request) -> JSONResponse:
        return await _refuse_phase(request, access, recorder, "commit-development-epoch")


def _install_read_routes(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    """Install only the two real read-only I1.7A operations."""

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
