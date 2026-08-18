"""HTTP boundary coverage for the movement JSON and Atom read adapters."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ctower_api._project_feed_atom_routes import install_project_feed_atom_routes
from ctower_api._project_movement_routes import install_project_movement_routes
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.access import Access
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem
from ctower_kernel.record.movement_events import MovementEvent, MovementEventPage

_TENANT_ID = UUID("10000000-0000-0000-0000-00000000aa01")
_PRINCIPAL_ID = UUID("20000000-0000-0000-0000-00000000aa01")
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_UNPROCESSABLE = 422
_PAGE_SIZE = 2


def _actor() -> Actor:
    return Actor(principal_id=_PRINCIPAL_ID, tenant_id=_TENANT_ID, kind=PrincipalKind.OPERATOR)


def _problem(code: str = "project-scope-denied", status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail="refused for test", status=status, title="Refused")


def _event(position: int) -> MovementEvent:
    return MovementEvent(
        event_id=uuid4(),
        record_position=position,
        ticket_id=uuid4(),
        from_stage="plan",
        to_stage="design",
        evaluation_ref=str(uuid4()),
        workflow_ref="engineering.software-factory@1",
        workflow_version=position,
        occurred_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )


class _Recorder:
    def emit(self, *_args: object, **_kwargs: object) -> None:
        return None


def _headers() -> dict[str, str]:
    command = uuid4()
    payload: dict[str, object] = {
        "schema": "ctower.telemetry-context/v1",
        "trace_id": secrets.token_hex(16),
        "span_id": secrets.token_hex(8),
        "trace_flags": 1,
        "correlation_id": str(command),
        "causation_id": str(command),
        "tenant_id": "unresolved",
        "actor_id": "unresolved",
        "command_id": str(command),
    }
    return {
        "Authorization": "Bearer test",
        "X-Ctower-Telemetry-Context": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


def _client(
    outcome: MovementEventPage | RecordProblem, *, actor: Actor | RecordProblem | None = None
) -> TestClient:
    app = FastAPI()
    access = cast(Access, SimpleNamespace(authenticate=lambda _credential: actor or _actor()))
    audit = SimpleNamespace(
        movement_events=lambda *_args, **_kwargs: outcome,
    )
    record = cast(Record, SimpleNamespace(event_audit=audit))
    recorder = cast(TelemetryRecorder, _Recorder())
    install_project_movement_routes(app, access, record, recorder)
    install_project_feed_atom_routes(app, access, record, recorder)
    return TestClient(app)


def _page(next_cursor: int | None = None) -> MovementEventPage:
    return MovementEventPage(
        project_key="ctower", events=(_event(1), _event(2)), next_cursor=next_cursor
    )


def test_movement_json_returns_the_page_payload() -> None:
    response = _client(_page(next_cursor=2)).get("/v1/projects/ctower/movement", headers=_headers())
    assert response.status_code == _HTTP_OK
    body = response.json()
    assert body["project_key"] == "ctower"
    assert [event["record_position"] for event in body["events"]] == [1, 2]
    assert body["next_cursor"] == _PAGE_SIZE


def test_movement_json_carries_the_store_refusal() -> None:
    response = _client(_problem()).get("/v1/projects/ctower/movement", headers=_headers())
    assert response.status_code == _HTTP_FORBIDDEN
    assert response.json()["code"] == "project-scope-denied"


def test_movement_json_refuses_an_invalid_project_key() -> None:
    response = _client(_page()).get("/v1/projects/BAD KEY/movement", headers=_headers())
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_movement_json_carries_the_authentication_refusal() -> None:
    refusal = _problem(code="auth-identity-unresolved", status=401)
    response = _client(_page(), actor=refusal).get(
        "/v1/projects/ctower/movement", headers=_headers()
    )
    assert response.status_code == _HTTP_UNAUTHORIZED


def test_movement_atom_renders_entries_and_next_link() -> None:
    response = _client(_page(next_cursor=2)).get(
        "/v1/projects/ctower/movement.atom", headers=_headers()
    )
    assert response.status_code == _HTTP_OK
    assert response.headers["content-type"].startswith("application/atom+xml")
    assert response.text.count("<entry") == _PAGE_SIZE
    assert 'rel="next"' in response.text


def test_movement_atom_carries_the_store_refusal() -> None:
    response = _client(_problem()).get("/v1/projects/ctower/movement.atom", headers=_headers())
    assert response.status_code == _HTTP_FORBIDDEN
