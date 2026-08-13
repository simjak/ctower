"""Real-boundary negative authorization fixtures for direct Request triage."""

from __future__ import annotations

import hashlib
import secrets
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row

from .acceptance import accept_pending_commands
from .server import application
from .telemetry import telemetry_headers
from .tenant_fixture import TenantFixture, provision_seat

__all__ = [
    "assert_command_id_reuse_cannot_cross_principal_authority",
    "assert_non_commander_project_seat_cannot_directly_triage",
    "assert_payload_authority_cannot_override_authenticated_principal",
    "assert_routine_held_seat_cannot_directly_triage",
]

HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE = 422


def assert_non_commander_project_seat_cannot_directly_triage(
    tenant: TenantFixture,
) -> None:
    """An owning project seat keeps its ordinary transition power, but not triage."""

    owner_id, owner_credential = provision_seat(tenant, "request-owner")
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        request_id = _capture(client, tenant, "A non-Commander owner cannot triage.")
        assigned = client.post(
            f"/v1/requests/{request_id}/owner",
            headers=_headers(tenant.operator_credential),
            json={
                "expected_version": 1,
                "owner_id": str(owner_id),
                "reason": "Give the project seat ordinary owner transitions.",
            },
        )
        assert assigned.status_code == HTTP_PENDING, assigned.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        blocked = client.post(
            f"/v1/requests/{request_id}/blockers",
            headers=_headers(owner_credential),
            json={
                "active": True,
                "blocker_key": "owner-boundary",
                "expected_version": 2,
                "reason": "Prove the owner seat has its allowed transition authority.",
            },
        )
        assert blocked.status_code == HTTP_PENDING, blocked.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        before = _request_residue(tenant, request_id)
        refused = _triage(client, owner_credential, request_id, expected_version=3)

    _assert_forbidden_without_mutation(tenant, request_id, before, refused)


def assert_routine_held_seat_cannot_directly_triage(tenant: TenantFixture) -> None:
    """A Routine's transition-scoped seat bearer cannot become direct triage authority."""

    routine_credential = secrets.token_urlsafe(32)
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        issued = client.post(
            "/v1/admin/seat-credentials",
            headers=_headers(tenant.operator_credential),
            json={
                "credential_digest": (
                    "sha256:" + hashlib.sha256(routine_credential.encode()).hexdigest()
                ),
                "credential_ref": "secret-ref:test/ctower/request-maintenance-routine",
                "display_name": "Request maintenance Routine",
                "project_key": "ctower",
                "scopes": ["transition"],
                "seat_key": "request-maintenance-routine",
            },
        )
        assert issued.status_code == HTTP_PENDING, issued.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        request_id = _capture(client, tenant, "A Routine-held seat cannot triage.")
        before = _request_residue(tenant, request_id)
        refused = _triage(client, routine_credential, request_id, expected_version=1)

    _assert_forbidden_without_mutation(tenant, request_id, before, refused)


def assert_payload_authority_cannot_override_authenticated_principal(
    tenant: TenantFixture,
) -> None:
    """Caller-supplied authority is rejected before it can override the bearer."""

    _, seat_credential = provision_seat(tenant, "payload-authority-prober")
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        request_id = _capture(client, tenant, "Payload authority cannot replace identity.")
        before = _request_residue(tenant, request_id)
        payload = _triage_payload(expected_version=1)
        payload["principal_id"] = str(tenant.operator_id)
        refused = client.post(
            f"/v1/requests/{request_id}/triage",
            headers=_headers(seat_credential),
            json=payload,
        )

    assert refused.status_code == HTTP_UNPROCESSABLE
    assert refused.json()["code"] == "validation-error"
    assert _request_residue(tenant, request_id) == before


def assert_command_id_reuse_cannot_cross_principal_authority(
    tenant: TenantFixture,
) -> None:
    """A second principal reaches its own refusal, never the operator's replay result."""

    seat_id, seat_credential = provision_seat(tenant, "command-replay-prober")
    command_id = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        request_id = _capture(client, tenant, "Command replay remains principal-scoped.")
        payload = _triage_payload(expected_version=1)
        accepted = client.post(
            f"/v1/requests/{request_id}/triage",
            headers=_headers(tenant.operator_credential, command_id),
            json=payload,
        )
        assert accepted.status_code == HTTP_PENDING, accepted.json()
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        after_operator = _request_residue(tenant, request_id)
        refused = client.post(
            f"/v1/requests/{request_id}/triage",
            headers=_headers(seat_credential, command_id),
            json=payload,
        )

    _assert_forbidden_without_mutation(tenant, request_id, after_operator, refused)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        results = connection.execute(
            """
            SELECT principal_id, status_code FROM command_results
            WHERE tenant_id = %s AND client_command_id = %s ORDER BY status_code
            """,
            (tenant.tenant_id, command_id),
        ).fetchall()
        events = connection.execute(
            """
            SELECT actor_principal_id FROM events
            WHERE tenant_id = %s AND client_command_id = %s AND kind = 'request.changed'
            """,
            (tenant.tenant_id, command_id),
        ).fetchall()
    assert results == [
        {"principal_id": tenant.operator_id, "status_code": 200},
        {"principal_id": seat_id, "status_code": HTTP_FORBIDDEN},
    ]
    assert events == [{"actor_principal_id": tenant.operator_id}]


def _capture(client: TestClient, tenant: TenantFixture, text: str) -> UUID:
    response = client.post(
        "/v1/requests",
        headers=_headers(tenant.commander_credential),
        json={"project_key": "ctower", "text": text},
    )
    assert response.status_code == HTTP_PENDING, response.json()
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return UUID(response.json()["request_id"])


def _triage(
    client: TestClient,
    credential: str,
    request_id: UUID,
    *,
    expected_version: int,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/requests/{request_id}/triage",
            headers=_headers(credential),
            json=_triage_payload(expected_version=expected_version),
        ),
    )


def _triage_payload(*, expected_version: int) -> dict[str, object]:
    return {
        "canonical_request_id": None,
        "disposition": "REJECTED",
        "expected_version": expected_version,
        "reason": "Direct triage authority boundary probe.",
    }


def _headers(credential: str, command_id: UUID | None = None) -> dict[str, str]:
    identity = command_id or uuid4()
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(identity),
        **telemetry_headers(identity),
    }


def _request_residue(tenant: TenantFixture, request_id: UUID) -> tuple[object, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT request.version,
                   (SELECT count(*) FROM events
                    WHERE stream_id = 'request:' || request.request_id::text),
                   (SELECT count(*) FROM request_triage_facts
                    WHERE request_id = request.request_id)
            FROM requests AS request WHERE request.request_id = %s
            """,
            (request_id,),
        ).fetchone()
    assert row is not None
    return cast(tuple[object, ...], row)


def _assert_forbidden_without_mutation(
    tenant: TenantFixture,
    request_id: UUID,
    before: tuple[object, ...],
    refused: Response,
) -> None:
    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "request-triage-forbidden"
    assert _request_residue(tenant, request_id) == before
