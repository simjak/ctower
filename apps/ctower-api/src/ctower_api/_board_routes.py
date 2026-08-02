"""Read-only HTTP adapter for the watermark-bearing Board projection."""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import BoardView as HttpBoardView
from ctower_client.models import Priority
from ctower_kernel.access import Access
from ctower_kernel.projections import BoardLane, BoardQuery, Projections
from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")


def install_board_routes(
    app: FastAPI,
    access: Access,
    projections: Projections,
    recorder: TelemetryRecorder,
) -> None:
    """Install the Board read; no projection mutation operation exists."""

    @app.get("/v1/board")
    def get_board(
        request: Request,
        lane: str | None = None,
        priority: str | None = None,
        stage_key: str | None = None,
        custodian_id: str | None = None,
        assignee_id: str | None = None,
        source_kind: str | None = None,
        source_ref: str | None = None,
    ) -> JSONResponse:
        actor = _authenticate(
            access,
            recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            query = BoardQuery(
                lane=BoardLane(lane) if lane is not None else None,
                priority=Priority(priority).value if priority is not None else None,
                stage_key=_stage_filter(stage_key),
                custodian_id=_uuid(custodian_id) if custodian_id is not None else None,
                assignee_id=_uuid(assignee_id) if assignee_id is not None else None,
                source_kind=_source_filter(source_kind, maximum=64),
                source_ref=_source_filter(source_ref, maximum=256),
            )
        except ValueError:
            return _problem_response(_validation_problem())
        view = projections.board(actor, query)
        boundary = HttpBoardView.model_validate_json(_encoded(view.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json"))


def _stage_filter(value: str | None) -> str | None:
    if value is not None and _STABLE_KEY.fullmatch(value) is None:
        raise ValueError("invalid stage filter")
    return value


def _source_filter(value: str | None, *, maximum: int) -> str | None:
    if value is not None and not 1 <= len(value) <= maximum:
        raise ValueError("invalid source filter")
    return value
