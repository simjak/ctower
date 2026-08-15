"""Protected spawn-record HTTP command adapter for R2982.

Append-only spawn records (create + transition facts) with project-scoped reads.
Inline Pydantic models (not generated) for P0 velocity; migrated to generated
schemas after codegen regeneration.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from ctower_api._http_support import (
    authenticate,
    problem_response,
    telemetry_context,
    uuid_value,
    validation_problem,
)
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.access import Access
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.runtime.spawn_records import (
    PostgresSpawnRecords,
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordList,
    SpawnRecordProblem,
    SpawnRecordTransitionCommand,
)

__all__: tuple[str, ...] = ()


def _to_record_problem(p: SpawnRecordProblem) -> RecordProblem:
    """Convert a SpawnRecordProblem to a RecordProblem for HTTP serialization."""
    return RecordProblem(
        code=p.code,
        detail=p.detail,
        status=p.status,
        title=p.title,
        command_id=p.command_id,
    )


class SpawnRecordCreateRequest(BaseModel):
    """Request payload to create a new spawn record."""

    project_key: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    seat_key: str = Field(pattern=r"^[a-z][a-z0-9._-]{0,95}$")
    crew_name: str = Field(min_length=1, max_length=255)
    task_file_ref: str = Field(min_length=1, max_length=1024)
    worktree_path: str = Field(min_length=1, max_length=1024)
    harness: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    effort: str | None = Field(default=None, min_length=1, max_length=64)
    workspace_id: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

    model_config = {"extra": "forbid"}


class SpawnRecordTransitionRequest(BaseModel):
    """Request payload to append a spawn lifecycle transition."""

    to_status: str = Field(pattern=r"^(accepted|running|completed|failed|reaped)$")
    reason: str | None = Field(default=None, min_length=1, max_length=4096)

    model_config = {"extra": "forbid"}


def install_spawn_record_routes(
    app: FastAPI,
    access: Access,
    spawn_records: PostgresSpawnRecords,
    recorder: TelemetryRecorder,
) -> None:
    """Bind the protected spawn-record command adapter."""

    _install_create_route(app, access, spawn_records, recorder)
    _install_transition_route(app, access, spawn_records, recorder)
    _install_list_route(app, access, spawn_records, recorder)
    _install_get_route(app, access, spawn_records, recorder)


def _install_create_route(
    app: FastAPI,
    access: Access,
    spawn_records: PostgresSpawnRecords,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/spawn-records")
    async def create_spawn_record(
        request: Request,
    ) -> JSONResponse:
        actor = authenticate(
            access,
            recorder,
            request,
            required_scope=CredentialScope.TRANSITION,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = SpawnRecordCreateRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("spawn.record", telemetry, outcome="ok", reason="requested")
        command = SpawnRecordCreate(
            client_command_id=command_id,
            project_key=payload.project_key,
            seat_key=payload.seat_key,
            crew_name=payload.crew_name,
            task_file_ref=payload.task_file_ref,
            worktree_path=payload.worktree_path,
            harness=payload.harness,
            model=payload.model,
            effort=payload.effort,
            workspace_id=UUID(payload.workspace_id) if payload.workspace_id else None,
        )
        result = spawn_records.create(
            actor.principal_id,
            actor.tenant_id,
            command,
            telemetry=telemetry,
        )
        if isinstance(result, SpawnRecordProblem):
            return problem_response(_to_record_problem(result))
        return JSONResponse(
            content=_get_payload(result),
            status_code=201,
        )


def _install_transition_route(
    app: FastAPI,
    access: Access,
    spawn_records: PostgresSpawnRecords,
    recorder: TelemetryRecorder,
) -> None:
    @app.post("/v1/spawn-records/{spawn_id}/transitions")
    async def append_spawn_transition(spawn_id: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access,
            recorder,
            request,
            required_scope=CredentialScope.TRANSITION,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            parsed_spawn_id = uuid_value(spawn_id)
            command_id = uuid_value(request.headers.get("Idempotency-Key"))
            payload = SpawnRecordTransitionRequest.model_validate_json(await request.body())
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        )
        recorder.emit("spawn.transition", telemetry, outcome="ok", reason=payload.to_status)
        command = SpawnRecordTransitionCommand(
            client_command_id=command_id,
            spawn_id=parsed_spawn_id,
            to_status=payload.to_status,
            reason=payload.reason,
        )
        result = spawn_records.transition(
            actor.principal_id,
            actor.tenant_id,
            command,
            telemetry=telemetry,
        )
        if isinstance(result, SpawnRecordProblem):
            return problem_response(_to_record_problem(result))
        return JSONResponse(
            content=_get_payload(result),
            status_code=200,
        )


def _install_list_route(
    app: FastAPI,
    access: Access,
    spawn_records: PostgresSpawnRecords,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/spawn-records")
    async def list_spawn_records(request: Request) -> JSONResponse:
        actor = authenticate(
            access,
            recorder,
            request,
            required_scope=CredentialScope.TRANSITION,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            project_key = request.query_params.get("project_key", "")
            if not project_key:
                return problem_response(validation_problem())
            status = request.query_params.get("status")
            limit = int(request.query_params.get("limit", "100"))
            offset = int(request.query_params.get("offset", "0"))
        except (ValidationError, ValueError):
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
        )
        result = spawn_records.list(
            actor.principal_id,
            actor.tenant_id,
            project_key,
            status=status,
            limit=min(limit, 1000),
            offset=max(offset, 0),
        )
        if isinstance(result, SpawnRecordProblem):
            return problem_response(_to_record_problem(result))
        return JSONResponse(
            content=_list_payload(result),
            status_code=200,
        )


def _install_get_route(
    app: FastAPI,
    access: Access,
    spawn_records: PostgresSpawnRecords,
    recorder: TelemetryRecorder,
) -> None:
    @app.get("/v1/spawn-records/{spawn_id}")
    async def get_spawn_record(spawn_id: str, request: Request) -> JSONResponse:
        actor = authenticate(
            access,
            recorder,
            request,
            required_scope=CredentialScope.TRANSITION,
        )
        if isinstance(actor, RecordProblem):
            return problem_response(actor)
        try:
            telemetry = telemetry_context(request)
            parsed_spawn_id = uuid_value(spawn_id)
        except ValueError:
            return problem_response(validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
        )
        result = spawn_records.get(
            actor.principal_id,
            actor.tenant_id,
            parsed_spawn_id,
        )
        if isinstance(result, SpawnRecordProblem):
            return problem_response(_to_record_problem(result))
        return JSONResponse(
            content=_get_payload(result),
            status_code=200,
        )


def _list_payload(result: SpawnRecordList) -> dict[str, object]:
    return {"records": [record.response_payload() for record in result.records]}


def _get_payload(result: SpawnRecordGet) -> dict[str, object]:
    r = result.record
    payload: dict[str, object] = {
        "spawn_id": str(r.spawn_id),
        "project_key": r.project_key,
        "seat_key": r.seat_key,
        "crew_name": r.crew_name,
        "task_file_ref": r.task_file_ref,
        "worktree_path": r.worktree_path,
        "harness": r.harness,
        "model": r.model,
        "status": r.status,
        "principal_id": str(r.principal_id),
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "transitions": [
            {
                "transition_id": str(t.transition_id),
                "from_status": t.from_status,
                "to_status": t.to_status,
                "reason": t.reason,
                "principal_id": str(t.principal_id),
                "transitioned_at": t.transitioned_at.isoformat(),
            }
            for t in r.transitions
        ],
    }
    if r.effort is not None:
        payload["effort"] = r.effort
    if r.workspace_id is not None:
        payload["workspace_id"] = str(r.workspace_id)
    return payload
