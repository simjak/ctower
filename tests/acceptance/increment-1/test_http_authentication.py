"""Authentication precedes validation on protected HTTP routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from support.http import app_for, operator_headers
from support.tenant_fixture import TenantFixture

__all__: tuple[str, ...] = ()

_ROUTES = (
    ("POST", "/v1/company/bundle/validate"),
    ("POST", "/v1/company/bundle/plan"),
    ("POST", "/v1/company/bundle/apply"),
    ("GET", "/v1/company/bundle/export"),
    ("POST", "/v1/tickets/not-a-uuid/comments"),
)


def test_new_routes_authenticate_before_path_or_body_validation(
    tenant: TenantFixture,
) -> None:
    authenticated_routes = (*_ROUTES[:3], _ROUTES[-1])
    with TestClient(app_for(tenant)) as client:
        unauthenticated = tuple(
            client.request(method, route, content=b"{") for method, route in _ROUTES
        )
        authenticated = tuple(
            client.request(
                method,
                route,
                content=b"{",
                headers=operator_headers(
                    tenant,
                    command_id=(
                        uuid4() if any(part in route for part in ("apply", "comments")) else None
                    ),
                ),
            )
            for method, route in authenticated_routes
        )

    assert {(response.status_code, response.json()["code"]) for response in unauthenticated} == {
        (401, "unauthorized")
    }
    assert {(response.status_code, response.json()["code"]) for response in authenticated} == {
        (422, "validation-error")
    }
