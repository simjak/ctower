"""Authenticated HTTP adapters for CompanyBundle authority."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api._mutation_response import mutation_response as _mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    CompanyBundleApplyRequest,
    CompanyBundleDocument,
    CompanyBundleExportResult,
    CompanyBundleRequest,
    CompanyBundleValidationResult,
)
from ctower_client.models import (
    CompanyBundleCommandResult as HttpCompanyBundleCommandResult,
)
from ctower_client.models import (
    CompanyBundlePlan as HttpCompanyBundlePlan,
)
from ctower_kernel.access import Access
from ctower_kernel.catalog import (
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    CompanyBundleExport,
    CompanyBundlePlan,
)
from ctower_kernel.record import Actor, Record, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


class BundleCatalog(Protocol):
    """Narrow API-facing CompanyBundle authority."""

    def validate(
        self, actor: Actor, bundle: CompanyBundle
    ) -> BundleValidation | CatalogProblem: ...

    def plan(self, actor: Actor, bundle: CompanyBundle) -> CompanyBundlePlan | CatalogProblem: ...

    def apply(
        self,
        actor: Actor,
        command: CompanyBundleApply,
        *,
        telemetry: TelemetryContext,
    ) -> CompanyBundleCommandResult | CatalogProblem: ...

    def export(self, actor: Actor) -> CompanyBundleExport | CatalogProblem: ...


def install_catalog_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    catalog: BundleCatalog,
    recorder: TelemetryRecorder,
) -> None:
    """Install the four authenticated CompanyBundle operations."""

    _install_validate(app, access, catalog, recorder)
    _install_plan(app, access, catalog, recorder)
    _install_apply(app, access, record, catalog, recorder)
    _install_export(app, access, catalog, recorder)


def _install_validate(
    app: FastAPI,
    access: Access,
    catalog: BundleCatalog,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/company/bundle/validate")
    async def validate(request: Request) -> JSONResponse:
        parsed = await _parse_bundle(access, recorder, request)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, bundle, _ = parsed
        outcome = catalog.validate(actor, bundle)
        return _catalog_response(outcome, CompanyBundleValidationResult)


def _install_plan(
    app: FastAPI,
    access: Access,
    catalog: BundleCatalog,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/company/bundle/plan")
    async def plan(request: Request) -> JSONResponse:
        parsed = await _parse_bundle(access, recorder, request)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, bundle, _ = parsed
        outcome = catalog.plan(actor, bundle)
        return _catalog_response(outcome, HttpCompanyBundlePlan)


def _install_apply(
    app: FastAPI,
    access: Access,
    record: Record,
    catalog: BundleCatalog,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/company/bundle/apply")
    async def apply(request: Request) -> JSONResponse:
        parsed = await _parse_apply(access, recorder, request)
        if isinstance(parsed, JSONResponse):
            return parsed
        actor, command, telemetry = parsed
        outcome = catalog.apply(actor, command, telemetry=telemetry)
        if isinstance(outcome, CatalogProblem):
            return _problem_response(outcome)
        return _mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command.client_command_id,
            telemetry=telemetry,
            boundary_model=HttpCompanyBundleCommandResult,
            accepted_status=200,
        )


def _install_export(
    app: FastAPI,
    access: Access,
    catalog: BundleCatalog,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/company/bundle/export")
    def export(request: Request) -> JSONResponse:
        authenticated = _authenticated(access, recorder, request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        actor, _ = authenticated
        outcome = catalog.export(actor)
        if isinstance(outcome, CatalogProblem):
            return _problem_response(outcome)
        boundary = CompanyBundleExportResult.model_validate_json(
            _encoded(
                {
                    "active_version": outcome.active_version,
                    "bundle": outcome.bundle.model_dump(mode="json", by_alias=True),
                    "bundle_digest": outcome.bundle_digest,
                    "metadata": {
                        "activated_at": outcome.activated_at.isoformat(),
                        "actor_principal_id": str(outcome.actor_principal_id),
                        "checks": tuple(check.model_dump(mode="json") for check in outcome.checks),
                        "command_id": str(outcome.command_id),
                    },
                }
            )
        )
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))


async def _parse_bundle(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
) -> tuple[Actor, CompanyBundle, TelemetryContext] | JSONResponse:
    authenticated = _authenticated(access, recorder, request)
    if isinstance(authenticated, JSONResponse):
        return authenticated
    actor, telemetry = authenticated
    try:
        payload = CompanyBundleRequest.model_validate_json(await request.body())
        bundle = _kernel_bundle(payload.bundle)
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    return actor, bundle, telemetry


async def _parse_apply(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
) -> tuple[Actor, CompanyBundleApply, TelemetryContext] | JSONResponse:
    actor = _authenticate(access, recorder, request)
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        command_id = _uuid(request.headers.get("Idempotency-Key"))
        payload = CompanyBundleApplyRequest.model_validate_json(await request.body())
        command = CompanyBundleApply(
            client_command_id=command_id,
            bundle=_kernel_bundle(payload.bundle),
            expected_active_version=payload.expected_active_version,
            plan_digest=payload.plan_digest,
        )
        telemetry = _actor_telemetry(request, actor, command_id=command_id)
    except (ValidationError, ValueError):
        return _problem_response(_validation_problem())
    _emit_authenticated(recorder, telemetry)
    return actor, command, telemetry


def _authenticated(
    access: Access,
    recorder: TelemetryRecorder,
    request: Request,
) -> tuple[Actor, TelemetryContext] | JSONResponse:
    actor = _authenticate(access, recorder, request)
    if isinstance(actor, RecordProblem):
        return _problem_response(actor)
    try:
        telemetry = _actor_telemetry(request, actor)
    except ValueError:
        return _problem_response(_validation_problem())
    _emit_authenticated(recorder, telemetry)
    return actor, telemetry


def _actor_telemetry(
    request: Request,
    actor: Actor,
    *,
    command_id: UUID | None = None,
) -> TelemetryContext:
    values = {
        "tenant_id": str(actor.tenant_id),
        "actor_id": str(actor.principal_id),
    }
    if command_id is not None:
        values["command_id"] = str(command_id)
    return _telemetry(request).bind(**values)


def _emit_authenticated(recorder: TelemetryRecorder, telemetry: TelemetryContext) -> None:
    recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")


def _kernel_bundle(document: CompanyBundleDocument) -> CompanyBundle:
    return CompanyBundle.model_validate_json(document.model_dump_json(by_alias=True))


def _catalog_response(
    outcome: BundleValidation | CompanyBundlePlan | CatalogProblem,
    boundary_model: type[CompanyBundleValidationResult | HttpCompanyBundlePlan],
) -> JSONResponse:
    if isinstance(outcome, CatalogProblem):
        return _problem_response(outcome)
    boundary = boundary_model.model_validate_json(
        _encoded(outcome.model_dump(mode="json", by_alias=True))
    )
    return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))
