"""Authenticated fail-loud health and poison-recovery HTTP adapters."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import encoded as _encoded
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import uuid_value as _uuid
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_client.models import ControlHealth as HttpControlHealth
from ctower_client.models import PoisonDispositionReceipt as HttpPoisonDispositionReceipt
from ctower_client.models import PoisonDispositionRequest
from ctower_kernel.access import Access
from ctower_kernel.attention import Attention, PoisonDisposition, PoisonDispositionAction
from ctower_kernel.projections import Projections
from ctower_kernel.record import Record, RecordProblem

__all__: tuple[str, ...] = ()


def install_health_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    projections: Projections,
    recorder: TelemetryRecorder,
    attention: Attention | None,
) -> None:
    """Install health reads and, when composed, protected recovery commands."""

    @app.get("/health")
    def get_control_health(request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        now = datetime.now(UTC)
        snapshot = projections.health(actor, record.durability_health(now=now), now=now)
        boundary = HttpControlHealth.model_validate_json(_encoded(snapshot.response_payload()))
        return JSONResponse(content=boundary.model_dump(mode="json", by_alias=True))

    if attention is not None:
        _install_disposition_route(app, access, recorder, attention)


def _install_disposition_route(
    app: FastAPI,
    access: Access,
    recorder: TelemetryRecorder,
    attention: Attention,
) -> None:
    @app.post("/v1/outbox/{outbox_id}/dispositions", status_code=202)
    async def record_disposition(outbox_id: str, request: Request) -> JSONResponse:
        actor = _authenticate(access, recorder, request)
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            parsed_outbox_id = _uuid(outbox_id)
            command_id = _uuid(request.headers.get("Idempotency-Key"))
            payload = PoisonDispositionRequest.model_validate_json(await request.body())
            command = PoisonDisposition(
                client_command_id=command_id,
                consumer_key=payload.consumer_key,
                topic=payload.topic,
                outbox_id=parsed_outbox_id,
                action=PoisonDispositionAction(payload.action.value),
                reason=payload.reason,
            )
            receipt = attention.disposition(actor, command)
        except (ValidationError, ValueError):
            return _problem_response(_validation_problem())
        boundary = HttpPoisonDispositionReceipt.model_validate_json(
            _encoded(receipt.response_payload())
        )
        return JSONResponse(
            status_code=202,
            headers={"Retry-After": "1"},
            content=boundary.model_dump(mode="json"),
        )
