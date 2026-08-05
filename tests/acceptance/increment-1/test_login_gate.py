"""Login-gate middleware matrix: authed/unauthed x browser/API x enforcing/not.

Builds the real ``create_app`` composition (the public control-API entrypoint) with a
placeholder Record, since the gate's own logic is what's under test and none of the
paths exercised here ever reach downstream Record access. The dummy probe route is a
stand-in for any authenticated agent surface.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ctower_api.interface import OidcRuntimeConfig, create_app
from ctower_kernel.record import Record

__all__: tuple[str, ...] = ()

_HTML_ACCEPT = {"accept": "text/html"}
_JSON_ACCEPT = {"accept": "application/json"}
_BEARER = {"authorization": "Bearer opaque-machine-credential"}
_SESSION_COOKIE = "__Host-ctower_session"


def _build_app(*, enforcing: bool) -> FastAPI:
    app = create_app(cast(Record, object()), oidc=OidcRuntimeConfig(gate_enforcing=enforcing))

    @app.get("/probe-surface")
    async def protected_surface() -> dict[str, bool]:
        return {"reached": True}

    return app


def test_enforcing_unauthed_browser_redirects_to_login() -> None:
    with TestClient(_build_app(enforcing=True), follow_redirects=False) as client:
        response = client.get("/probe-surface", headers=_HTML_ACCEPT)

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["location"].startswith("/auth/login")


def test_enforcing_unauthed_api_refuses_with_named_problem() -> None:
    with TestClient(_build_app(enforcing=True), follow_redirects=False) as client:
        response = client.get("/probe-surface", headers=_JSON_ACCEPT)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["content-type"].partition(";")[0] == "application/problem+json"
    payload = response.json()
    assert payload["code"] == "unauthorized"


def test_enforcing_authed_via_bearer_reaches_the_route_regardless_of_accept() -> None:
    with TestClient(_build_app(enforcing=True), follow_redirects=False) as client:
        browser = client.get("/probe-surface", headers={**_HTML_ACCEPT, **_BEARER})
        api = client.get("/probe-surface", headers={**_JSON_ACCEPT, **_BEARER})

    assert browser.status_code == HTTPStatus.OK
    assert browser.json() == {"reached": True}
    assert api.status_code == HTTPStatus.OK
    assert api.json() == {"reached": True}


def test_enforcing_authed_via_session_cookie_reaches_the_route() -> None:
    with TestClient(_build_app(enforcing=True), follow_redirects=False) as client:
        client.cookies.set(_SESSION_COOKIE, "opaque-session-value")
        response = client.get("/probe-surface", headers=_HTML_ACCEPT)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"reached": True}


def test_enforcing_never_gates_the_auth_routes_themselves() -> None:
    with TestClient(_build_app(enforcing=True), follow_redirects=False) as client:
        response = client.get("/auth/login", headers=_HTML_ACCEPT)

    # Unconfigured providers still refuse (no redirect loop), but as the auth route's
    # own named refusal, never the gate's redirect/401.
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["code"] == "auth-provider-unavailable"


def test_dark_state_never_enforces_regardless_of_credential_or_accept() -> None:
    """Revert-probe: the default (present-but-not-enforcing) gate changes nothing."""

    with TestClient(_build_app(enforcing=False), follow_redirects=False) as client:
        no_credential_browser = client.get("/probe-surface", headers=_HTML_ACCEPT)
        no_credential_api = client.get("/probe-surface", headers=_JSON_ACCEPT)
        bearer = client.get("/probe-surface", headers={**_JSON_ACCEPT, **_BEARER})

    for response in (no_credential_browser, no_credential_api, bearer):
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"reached": True}
