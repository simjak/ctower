"""Read-only HTTP adapter for the accepted project event feed."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import ProjectEventPage as HttpProjectEventPage
from ctower_kernel.access import Access
from ctower_kernel.record import ProjectEventCursor, Record, RecordProblem

__all__: tuple[str, ...] = ()


def install_project_event_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install one project-scoped feed over accepted canonical events."""

    @app.get("/v1/projects/{project_key}/events")
    def list_project_events(
        project_key: str,
        request: Request,
        cursor: str | None = None,
        limit: int = 50,
    ) -> JSONResponse:
        actor = _authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            initial_cursor = ProjectEventCursor(project_key, 0, 0)
            page_cursor = (
                ProjectEventCursor.decode(cursor) if cursor is not None else initial_cursor
            )
            telemetry = _telemetry(request).bind(
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.principal_id),
            )
        except ValueError:
            return _problem_response(_validation_problem())
        outcome = record.project_events(
            actor,
            project_key,
            page_cursor,
            limit=limit,
            telemetry=telemetry,
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        try:
            boundary = HttpProjectEventPage.model_validate_json(
                _encoded(outcome.response_payload())
            )
        except ValidationError as error:
            raise RuntimeError("Record returned an invalid project event page") from error
        return JSONResponse(content=boundary.model_dump(mode="json"))
