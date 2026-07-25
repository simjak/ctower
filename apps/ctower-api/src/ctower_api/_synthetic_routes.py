"""Protected HTTP adapters for the one fixed synthetic operation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import (
    authenticate,
    encoded,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api._mutation_response import mutation_response
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import (
    SyntheticRunReceipt as HttpSyntheticRunReceipt,
)
from ctower_client.models import (
    SyntheticRunRequest,
    SyntheticRunResource,
)
from ctower_kernel.access import Access
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.runtime import (
    RoutineRevision,
    SyntheticRun,
    SyntheticRunCommand,
    SyntheticRunReceipt,
)

__all__: tuple[str, ...] = ()


class SyntheticRuntime(Protocol):
    def start_synthetic(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command: SyntheticRunCommand,
        revision: RoutineRevision,
    ) -> SyntheticRunReceipt | RecordProblem: ...

    def synthetic_run(self, tenant_id: UUID, run_id: UUID) -> SyntheticRun | None: ...


def install_synthetic_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    runtime: SyntheticRuntime,
    revision: RoutineRevision,
    recorder: TelemetryRecorder,
) -> None:
    """Install strict run/read operations without executing inside the request."""

    _install_run(app, access, record, runtime, revision, recorder)
    _install_get(app, access, runtime, recorder)


def _install_run(
    app: FastAPI,
    access: Access,
    record: Record,
    runtime: SyntheticRuntime,
    revision: RoutineRevision,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/control/synthetic-runs")
    async def run_synthetic(request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = SyntheticRunRequest.model_validate_json(await request.body())
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
                command_id=str(command_id),
            )
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = runtime.start_synthetic(
            actor.tenant_id,
            actor.principal_id,
            SyntheticRunCommand(command_id, payload.workflow_ref),
            revision,
        )
        return mutation_response(
            record,
            outcome,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            command_id=command_id,
            telemetry=telemetry,
            boundary_model=HttpSyntheticRunReceipt,
            accepted_status=201,
        )


def _install_get(
    app: FastAPI,
    access: Access,
    runtime: SyntheticRuntime,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/control/synthetic-runs/{run_id}")
    def get_synthetic(run_id: str, request: Request) -> JSONResponse:
        actor = authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            parsed = uuid_value(run_id)
            telemetry = telemetry_context(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
            )
        except ValueError:
            return problem_response(validation_problem())
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = runtime.synthetic_run(actor.tenant_id, parsed)
        if outcome is None:
            return problem_response(
                RecordProblem(
                    code="tenant-scope-denied",
                    detail="Synthetic run unavailable.",
                    status=404,
                    title="Synthetic run unavailable",
                )
            )
        boundary = SyntheticRunResource.model_validate_json(encoded(_resource(outcome)))
        return JSONResponse(content=boundary.model_dump(mode="json"))


def _resource(run: SyntheticRun) -> dict[str, object]:
    return {
        "attempt_count": run.attempt_count,
        "completed_at": run.completed_at.isoformat() if run.completed_at is not None else None,
        "created_at": run.created_at.isoformat(),
        "detail_code": run.detail_code,
        "job_id": str(run.job_id),
        "lifecycle_facts": list(run.lifecycle_facts),
        "run_id": str(run.run_id),
        "state": run.state.value,
        "ticket_id": str(run.ticket_id) if run.ticket_id is not None else None,
        "workflow_ref": run.workflow_ref,
    }
