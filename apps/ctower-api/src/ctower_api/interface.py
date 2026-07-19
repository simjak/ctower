"""Thin HTTP composition over generated boundaries and kernel Interfaces."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from ctower_client.models import BootstrapReceipt as HttpBootstrapReceipt
from ctower_client.models import BootstrapRequest, Problem
from ctower_kernel.access import Access
from ctower_kernel.record import BootstrapCommand, BootstrapReceipt, BootstrapRecord, RecordProblem

__all__ = ["create_app"]


def create_app(record: BootstrapRecord) -> FastAPI:
    """Compose the private command API without embedding durable decisions."""

    app = FastAPI(title="ctower control API", version="0.0.0")
    access = Access(record)

    @app.post("/v1/bootstrap/first-tenant", status_code=201)
    def bootstrap_first_tenant(
        request: Request,
        payload: BootstrapRequest,
        command_id: Annotated[UUID, Header(alias="Idempotency-Key")],
        capability: Annotated[str, Header(alias="X-Ctower-Bootstrap-Capability")],
    ) -> JSONResponse:
        origin = request.client.host if request.client is not None else ""
        outcome = access.bootstrap_first_tenant(
            BootstrapCommand(
                client_command_id=command_id,
                commander_name=payload.commander_name,
                commander_vault_ref=payload.commander_vault_ref,
                operator_credential_ref=payload.operator_credential_ref,
                operator_name=payload.operator_name,
                operator_vault_ref=payload.operator_vault_ref,
                tenant_name=payload.tenant_name,
                tenant_slug=payload.tenant_slug,
            ),
            capability=capability,
            origin=origin,
        )
        return _response(outcome)

    return app


def _response(outcome: BootstrapReceipt | RecordProblem) -> JSONResponse:
    payload = outcome.response_payload()
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if isinstance(outcome, BootstrapReceipt):
        receipt_boundary = HttpBootstrapReceipt.model_validate_json(encoded)
        return JSONResponse(status_code=201, content=receipt_boundary.model_dump(mode="json"))
    problem_boundary = Problem.model_validate_json(encoded)
    return JSONResponse(
        status_code=outcome.status,
        content=problem_boundary.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )
