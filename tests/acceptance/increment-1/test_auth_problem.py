"""Raw authority precedence and RFC 9457 failure acceptance evidence."""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()


def test_authentication_precedes_malformed_body_and_path_validation(
    tenant: TenantFixture,
) -> None:
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        missing = client.post("/v1/tickets", content=b"{")
        wrong = client.post("/v1/tickets", content=b"{", headers={"Authorization": "Bearer wrong"})
        malformed_path = client.get("/v1/tickets/not-a-uuid")
        invalid = client.post(
            "/v1/tickets",
            content=b"{",
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                **telemetry_headers(),
            },
        )
        invalid_path = client.get(
            "/v1/tickets/not-a-uuid",
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                **telemetry_headers(),
            },
        )

    for response in (missing, wrong, malformed_path):
        _assert_problem(response, 401, "unauthorized")
    for response in (invalid, invalid_path):
        _assert_problem(response, 422, "validation-error")


def _assert_problem(response: Response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].partition(";")[0] == "application/problem+json"
    payload = response.json()
    assert payload["code"] == code
    assert set(payload) >= {"code", "detail", "status", "title", "type"}
    assert payload["status"] == status
    assert payload["type"] == f"https://ctower.dev/problems/{code}"
