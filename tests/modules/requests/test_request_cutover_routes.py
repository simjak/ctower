"""Hidden Request cutover HTTP boundary behavior."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ctower_api import _request_cutover_routes as module
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.request_cutover import (
    RequestCutoverResult,
    RequestImportReconciliation,
)

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + "1" * 64
_VALIDATION_STATUS = 422
_ROUTE_COUNT = 6


class _Cutover:
    def __init__(self) -> None:
        self.outcome: RequestCutoverResult | RecordProblem = RequestCutoverResult(
            uuid4(), "prepare", _DIGEST, "prepared", 1, 2, event_ids=(uuid4(),)
        )
        self.reconciliation: RequestImportReconciliation | RecordProblem = (
            RequestImportReconciliation(
                _DIGEST,
                0,
                1,
                {"ctower": 1},
                1,
                {"ctower": 1},
                1,
                {"ctower": 1},
                1,
                {"ctower": 1},
                2,
                (),
                (),
            )
        )
        self.calls: list[str] = []

    def authority_inventory(self, _actor: Actor) -> dict[str, object] | RecordProblem:
        self.calls.append("inventory")
        return self.outcome if isinstance(self.outcome, RecordProblem) else {"ready": True}

    def prepare(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("prepare")
        return self.outcome

    def import_row(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("import")
        return self.outcome

    def reconcile(
        self, *_args: object, **_kwargs: object
    ) -> RequestImportReconciliation | RecordProblem:
        self.calls.append("reconcile")
        return self.reconciliation

    def record_batch_proof(
        self, *_args: object, **_kwargs: object
    ) -> RequestCutoverResult | RecordProblem:
        self.calls.append("proof")
        return self.outcome

    def complete(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("complete")
        return self.outcome


def test_hidden_routes_parse_and_dispatch_every_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    cutover = _Cutover()
    routes = _routes(monkeypatch, cutover)
    command_id = uuid4()

    assert _payload(routes.inventory(_request())) == {"ready": True}
    prepared = asyncio.run(routes.prepare(_request(_prepare_body(), command_id=command_id)))
    imported = asyncio.run(routes.import_row(_request(_import_body(), command_id=command_id)))
    reconciled = routes.reconcile(_request(), _DIGEST, 0)
    proved = asyncio.run(routes.record_proof(_request(_proof_body(), command_id=command_id)))
    completed = asyncio.run(routes.complete(_request(_complete_body(), command_id=command_id)))

    assert tuple(response.status_code for response in (prepared, imported, proved, completed)) == (
        202,
        201,
        202,
        202,
    )
    assert _payload(reconciled)["manifest_digest"] == _DIGEST
    assert cutover.calls == ["inventory", "prepare", "import", "reconcile", "proof", "complete"]


def test_hidden_routes_fail_closed_at_auth_shape_size_and_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutover = _Cutover()
    routes = _routes(monkeypatch, cutover)
    problem = _problem()
    cutover.outcome = problem
    cutover.reconciliation = problem

    assert routes.inventory(_request()).status_code == problem.status
    assert routes.reconcile(_request(), _DIGEST, 0).status_code == problem.status
    assert routes.reconcile(_request(), _DIGEST, -1).status_code == _VALIDATION_STATUS
    refused = asyncio.run(routes.prepare(_request(_prepare_body(), command_id=uuid4())))
    assert refused.status_code == problem.status

    monkeypatch.setattr(module, "authenticate", lambda *_args, **_kwargs: problem)
    assert routes.inventory(_request()).status_code == problem.status
    assert asyncio.run(routes.import_row(_request(_import_body()))).status_code == problem.status
    assert routes.reconcile(_request(), _DIGEST, 0).status_code == problem.status
    assert asyncio.run(routes.record_proof(_request(_proof_body()))).status_code == problem.status
    assert asyncio.run(routes.complete(_request(_complete_body()))).status_code == problem.status


def test_hidden_mutations_refuse_invalid_headers_bodies_and_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes = _routes(monkeypatch, _Cutover())
    invalid_header = asyncio.run(routes.prepare(_request(_prepare_body())))
    invalid_json = asyncio.run(routes.prepare(_request(b"{", command_id=uuid4())))
    invalid_shape = asyncio.run(routes.prepare(_request(b"{}", command_id=uuid4())))
    monkeypatch.setattr(module, "_BODY_LIMIT", 1)
    oversized = asyncio.run(routes.prepare(_request(b"{}", command_id=uuid4())))
    assert all(
        response.status_code == _VALIDATION_STATUS
        for response in (invalid_header, invalid_json, invalid_shape, oversized)
    )


def test_route_installation_is_hidden_from_openapi() -> None:
    cutover = _Cutover()
    app = FastAPI()
    module.install_request_cutover_routes(
        app,
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, cutover),
        cast(Any, object()),
    )
    hidden = [
        cast(str, cast(Any, route).path)
        for route in app.routes
        if cast(str, getattr(route, "path", "")).startswith("/_internal/request-cutover")
    ]
    assert len(hidden) == _ROUTE_COUNT
    assert all(path not in app.openapi()["paths"] for path in hidden)


def _routes(monkeypatch: pytest.MonkeyPatch, cutover: _Cutover) -> module._RequestCutoverRoutes:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    monkeypatch.setattr(module, "authenticate", lambda *_args, **_kwargs: actor)
    monkeypatch.setattr(module, "telemetry_context", lambda _request: _context())

    def mutation_response(
        _record: object,
        outcome: RequestCutoverResult | RecordProblem,
        **kwargs: object,
    ) -> JSONResponse:
        if isinstance(outcome, RecordProblem):
            return JSONResponse({"code": outcome.code}, status_code=outcome.status)
        return JSONResponse(
            outcome.response_payload(), status_code=cast(int, kwargs["accepted_status"])
        )

    monkeypatch.setattr(module, "mutation_response", mutation_response)
    return module._RequestCutoverRoutes(
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, cutover),
        cast(Any, object()),
    )


def _request(body: bytes = b"", *, command_id: object | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if command_id is not None:
        headers.append((b"idempotency-key", str(command_id).encode()))

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "root_path": "",
    }
    return Request(cast(Any, scope), receive)


def _prepare_body() -> bytes:
    return _json({"manifest": "{}", "fence": "{}", "reviewer_public_key_pem": "pem"})


def _import_body() -> bytes:
    return _json(
        {
            "manifest_digest": _DIGEST,
            "source_request_id": "R1",
            "content": "frozen intent",
            "fence": "{}",
            "reviewer_public_key_pem": "pem",
        }
    )


def _proof_body() -> bytes:
    return _json({"proof": "{}", "reviewer_public_key_pem": "pem"})


def _complete_body() -> bytes:
    return _json(
        {"manifest_digest": _DIGEST, "final_fence": "{}", "reviewer_public_key_pem": "pem"}
    )


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _payload(response: JSONResponse) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(bytes(response.body)))


def _problem() -> RecordProblem:
    return RecordProblem("request-import-forbidden", "absent", 404, "Absent")


def _context() -> TelemetryContext:
    command_id = uuid4()
    return TelemetryContext(
        "ctower.telemetry-context/v1",
        command_id.hex,
        command_id.hex[:16],
        1,
        str(command_id),
        str(command_id),
        "unresolved",
        "unresolved",
        str(command_id),
    )
