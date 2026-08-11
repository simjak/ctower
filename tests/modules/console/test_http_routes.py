"""HTTP boundary coverage for Console Phase 1 operator and browser refusals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ctower_api.console_network import ConsoleListenerError
from ctower_api.console_routes import ConsoleRuntime, install_console_routes
from ctower_kernel.access import Access
from ctower_kernel.console import (
    ConsoleEventStream,
    ConsoleSessionAllowance,
    ConsoleViewer,
    ConsoleViewGrant,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

_ORIGIN = "https://100.84.252.114:8443"
_TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
_OPERATOR_ID = UUID("20000000-0000-0000-0000-000000000001")
_VIEWER_ID = UUID("30000000-0000-0000-0000-000000000001")
_ALLOWANCE_ID = UUID("40000000-0000-0000-0000-000000000001")
_GRANT_ID = UUID("50000000-0000-0000-0000-000000000001")
_PREVIOUS_GRANT_ID = UUID("50000000-0000-0000-0000-000000000002")
_SESSION_ID = UUID("60000000-0000-0000-0000-000000000001")
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_UNAUTHORIZED = 401
_HTTP_UNPROCESSABLE = 422


def _problem(code: str = "console-session-unavailable", status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail="refused for test", status=status, title="Refused")


@dataclass(slots=True)
class _Human:
    outcome: object

    def authenticate_browser_session(
        self, session_token: str | None, *, csrf_token: str | None
    ) -> object:
        if session_token is None or csrf_token is None:
            return _problem("auth-session-invalid", 401)
        return self.outcome


@dataclass(slots=True)
class _Access:
    actor: Actor | RecordProblem
    human: _Human

    def authenticate(self, authorization: str | None) -> Actor | RecordProblem:
        if authorization != "Bearer operator":
            return _problem("unauthorized", 401)
        return self.actor


class _Viewer:
    def __init__(self, actor: Actor) -> None:
        now = datetime(2026, 8, 11, tzinfo=UTC)
        self.allowance = ConsoleSessionAllowance(
            allowance_id=_ALLOWANCE_ID,
            tenant_id=_TENANT_ID,
            project_key="ctower",
            recorded_work_session_id=_SESSION_ID,
            crew_name="engineer-console-p1",
            allowed_at=now,
        )
        self.grant = cast(
            ConsoleViewGrant,
            SimpleNamespace(
                grant_id=_GRANT_ID,
                allowance_id=_ALLOWANCE_ID,
                project_key="ctower",
                policy_revision="console-phase1-r1",
                not_before=now,
                expires_at=now + timedelta(minutes=5),
                maximum_uses=1,
                renewed_from_grant_id=None,
            ),
        )
        self.actor = actor
        self.outcome: object | None = None
        self.calls: list[tuple[str, object]] = []

    def allow_session(self, actor: Actor, command: object) -> object:
        del actor
        self.calls.append(("allow", command))
        return self.outcome if self.outcome is not None else self.allowance

    def revoke_session(self, actor: Actor, command: object) -> RecordProblem | None:
        del actor
        self.calls.append(("revoke", command))
        return cast(RecordProblem | None, self.outcome)

    def set_global_switch(self, actor: Actor, command: object) -> RecordProblem | None:
        del actor
        self.calls.append(("switch", command))
        return cast(RecordProblem | None, self.outcome)

    def visible_sessions(self, actor: Actor) -> object:
        self.calls.append(("visible", actor))
        return self.outcome if self.outcome is not None else (self.allowance,)

    def mint_grant(self, actor: Actor, allowance_id: UUID, *, renewal: bool) -> object:
        del actor, allowance_id
        self.calls.append(("grant", renewal))
        if self.outcome is not None:
            return self.outcome
        if renewal:
            self.grant = cast(
                ConsoleViewGrant,
                SimpleNamespace(
                    **{
                        **vars(self.grant),
                        "renewed_from_grant_id": _PREVIOUS_GRANT_ID,
                    }
                ),
            )
        return self.grant

    def open_stream(self, actor: Actor, allowance_id: UUID, *, last_event_id: int | None) -> object:
        del actor, allowance_id
        self.calls.append(("stream", last_event_id))
        if self.outcome is not None:
            return self.outcome
        return cast(
            ConsoleEventStream,
            SimpleNamespace(
                events=iter((b"event: closed\n\n",)),
                maximum_pending_bytes=256 * 1024,
                maximum_stall_seconds=5,
                close_slow_consumer=lambda: (),
            ),
        )


def _app() -> tuple[FastAPI, _Access, _Viewer]:
    operator = Actor(_OPERATOR_ID, _TENANT_ID, PrincipalKind.OPERATOR)
    browser_actor = Actor(_VIEWER_ID, _TENANT_ID, PrincipalKind.VIEWER)
    access = _Access(operator, _Human(SimpleNamespace(actor=browser_actor)))
    viewer = _Viewer(browser_actor)
    app = FastAPI()
    install_console_routes(
        app,
        cast(Access, access),
        ConsoleRuntime(cast(ConsoleViewer, viewer), _ORIGIN),
    )
    return app, access, viewer


def _allow_payload() -> dict[str, object]:
    return {
        "adapter_key": "tmux-v1",
        "assignment_interval_sequence": 1,
        "assignment_kind": "implementation",
        "assignment_ticket_id": "70000000-0000-0000-0000-000000000001",
        "backend_incarnation": "$9:1786400000",
        "crew_name": "engineer-console-p1",
        "loop_kind": "standard",
        "opaque_backend_ref": "crew:engineer-console-p1",
        "project_key": "ctower",
        "recorded_work_session_id": str(_SESSION_ID),
        "runner_epoch": 7,
        "runner_id": "mission-control",
        "runtime_attempt_id": "80000000-0000-0000-0000-000000000001",
        "seat_principal_id": str(_VIEWER_ID),
        "sensitivity_class": "restricted",
    }


def _browser_headers(*, cursor: str | None = None) -> dict[str, str]:
    headers = {"Origin": _ORIGIN, "X-Ctower-CSRF": "csrf-token"}
    if cursor is not None:
        headers["Last-Event-ID"] = cursor
    return headers


def _client(app: FastAPI) -> TestClient:
    client = TestClient(app, base_url=_ORIGIN)
    client.cookies.set("__Host-ctower_session", "browser-session")
    client.cookies.set("__Host-ctower_csrf", "csrf-token")
    return client


@pytest.mark.parametrize(
    "origin",
    [
        "http://100.84.252.114:8443",
        "https://0.0.0.0:8443",
        "https://203.0.113.10:8443",
        "https://console.private.test:8443",
        "https://100.84.252.114:8443/path",
        "https://100.84.252.114",
    ],
)
def test_console_runtime_refuses_any_origin_that_is_not_the_exact_private_listener(
    origin: str,
) -> None:
    with pytest.raises(ConsoleListenerError):
        ConsoleRuntime(cast(ConsoleViewer, object()), origin)


def test_operator_routes_accept_strict_commands_and_return_typed_receipts() -> None:
    app, _access, viewer = _app()
    with TestClient(app) as client:
        allowed = client.post(
            "/v1/admin/console/sessions",
            headers={"Authorization": "Bearer operator"},
            json=_allow_payload(),
        )
        revoked = client.post(
            f"/v1/admin/console/sessions/{_ALLOWANCE_ID}/revocation",
            headers={"Authorization": "Bearer operator"},
            json={"reason": "operator revocation"},
        )
        switched = client.post(
            "/v1/admin/console/kill-switch",
            headers={"Authorization": "Bearer operator"},
            json={"enabled": True, "reason": "incident containment"},
        )

    assert allowed.status_code == _HTTP_CREATED
    assert allowed.json()["console_session_id"] == str(_ALLOWANCE_ID)
    assert revoked.status_code == _HTTP_NO_CONTENT
    assert revoked.content == b""
    assert "content-length" not in revoked.headers
    assert switched.status_code == _HTTP_NO_CONTENT
    assert switched.content == b""
    assert "content-length" not in switched.headers
    assert [name for name, _value in viewer.calls] == ["allow", "revoke", "switch"]


def test_operator_routes_fail_closed_on_auth_validation_and_authority_refusal() -> None:
    app, access, viewer = _app()
    with TestClient(app) as client:
        assert (
            client.post("/v1/admin/console/sessions", json=_allow_payload()).status_code
            == _HTTP_UNAUTHORIZED
        )
        invalid = client.post(
            "/v1/admin/console/sessions",
            headers={"Authorization": "Bearer operator"},
            json={"adapter_key": "tmux-v1"},
        )
        invalid_revoke = client.post(
            f"/v1/admin/console/sessions/{_ALLOWANCE_ID}/revocation",
            headers={"Authorization": "Bearer operator"},
            json={"reason": ""},
        )
        invalid_switch = client.post(
            "/v1/admin/console/kill-switch",
            headers={"Authorization": "Bearer operator"},
            json={"enabled": "yes", "reason": "invalid strict boolean"},
        )
        viewer.outcome = _problem("console-kill-switch-refused")
        authority_refused = client.post(
            "/v1/admin/console/kill-switch",
            headers={"Authorization": "Bearer operator"},
            json={"enabled": False, "reason": "refusal path"},
        )
        access.actor = _problem("console-role-refused")
        refused_actor = client.post(
            f"/v1/admin/console/sessions/{_ALLOWANCE_ID}/revocation",
            headers={"Authorization": "Bearer operator"},
            json={"reason": "must not reach authority"},
        )
        refused_switch_actor = client.post(
            "/v1/admin/console/kill-switch",
            headers={"Authorization": "Bearer operator"},
            json={"enabled": True, "reason": "must not reach authority"},
        )

    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert invalid_revoke.status_code == _HTTP_UNPROCESSABLE
    assert invalid_switch.status_code == _HTTP_UNPROCESSABLE
    assert authority_refused.json()["code"] == "console-kill-switch-refused"
    assert refused_actor.json()["code"] == "console-role-refused"
    assert refused_switch_actor.json()["code"] == "console-role-refused"


def test_browser_routes_cover_renewal_cursor_and_stream_response_contracts() -> None:
    app, _access, viewer = _app()
    with _client(app) as client:
        visible = client.get("/v1/console/sessions", headers=_browser_headers())
        minted = client.post(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/grants", headers=_browser_headers()
        )
        renewed = client.post(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/renewals", headers=_browser_headers()
        )
        streamed = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events",
            headers=_browser_headers(cursor="0"),
        )

    assert visible.status_code == _HTTP_OK
    assert minted.status_code == _HTTP_CREATED
    assert renewed.status_code == _HTTP_CREATED
    assert renewed.json()["renewed_from_grant_id"] == str(_PREVIOUS_GRANT_ID)
    assert streamed.status_code == _HTTP_OK
    assert streamed.headers["cache-control"] == "no-store"
    assert streamed.headers["x-accel-buffering"] == "no"
    assert streamed.text == "event: closed\n\n"
    assert ("stream", 0) in viewer.calls


def test_browser_routes_return_each_pre_stream_refusal_without_opening_output() -> None:
    app, access, viewer = _app()
    with _client(app) as client:
        missing_origin = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events",
            headers={"X-Ctower-CSRF": "csrf-token"},
        )
        missing_csrf = client.post(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/grants",
            headers={"Origin": _ORIGIN},
        )
        malformed = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events",
            headers=_browser_headers(cursor="not-a-cursor"),
        )
        negative = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events",
            headers=_browser_headers(cursor="-1"),
        )
        oversized = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events",
            headers=_browser_headers(cursor=str(2**63)),
        )
        query_credential = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events?grant=must-not-enter",
            headers=_browser_headers(),
        )
        calls_before_authority_refusal = tuple(viewer.calls)
        viewer.outcome = _problem("console-grant-unavailable")
        refused_stream = client.get(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/events", headers=_browser_headers()
        )
        refused_visible = client.get("/v1/console/sessions", headers=_browser_headers())
        refused_grant = client.post(
            f"/v1/console/sessions/{_ALLOWANCE_ID}/grants", headers=_browser_headers()
        )
        access.human.outcome = _problem("auth-session-invalid", 401)
        refused_browser = client.get("/v1/console/sessions", headers=_browser_headers())

    assert missing_origin.json()["code"] == "console-origin-refused"
    assert missing_csrf.json()["code"] == "console-csrf-invalid"
    assert malformed.json()["code"] == "console-cursor-invalid"
    assert negative.json()["code"] == "console-cursor-invalid"
    assert oversized.json()["code"] == "console-cursor-invalid"
    assert query_credential.status_code == _HTTP_UNPROCESSABLE
    assert query_credential.json()["code"] == "console-stream-query-refused"
    assert not any(call[0] == "stream" for call in calls_before_authority_refusal)
    assert refused_stream.json()["code"] == "console-grant-unavailable"
    assert refused_visible.json()["code"] == "console-grant-unavailable"
    assert refused_grant.json()["code"] == "console-grant-unavailable"
    assert refused_browser.json()["code"] == "auth-session-invalid"


__all__: tuple[str, ...] = ()
