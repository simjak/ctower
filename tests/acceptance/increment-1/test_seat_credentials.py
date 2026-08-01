"""Issued, scoped, revocable project-seat credential acceptance."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE = 422


def test_initial_custody_requires_an_explicit_project_grant(tenant: TenantFixture) -> None:
    ungranted_commander = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', 'Ungranted Commander', false, %s)
            """,
            (ungranted_commander, tenant.tenant_id, datetime.now(UTC)),
        )
    with _client(tenant) as client:
        refused = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(ungranted_commander),
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "grant-required"},
                    "title": "No implicit project authority",
                },
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )

    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "project-grant-required"


def test_operator_issues_capture_scope_and_seat_self_places_project_custody(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    command_id = uuid4()
    with _client(tenant) as client:
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=command_id,
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )
        replay = _issue(
            client,
            tenant.operator_credential,
            command_id=command_id,
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )

        assert issued.status_code == HTTP_PENDING
        assert replay.content == issued.content
        receipt = issued.json()
        assert receipt["project_key"] == "manibo"
        assert receipt["seat_key"] == "manibo-commander"
        assert receipt["scopes"] == ["capture"]
        assert receipt["state"] == "active"
        assert "credential" not in receipt

        created = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "manibo-R115"},
                    "title": "Manibo seat-owned ticket",
                },
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )
        transition = cast(
            Response,
            client.post(
                f"/v1/tickets/{created.json()['ticket']['ticket_id']}/priority",
                json={"expected_version": 1, "priority": "P1", "reason": "Scope probe"},
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )

    assert created.status_code == HTTP_PENDING
    assert transition.status_code == HTTP_FORBIDDEN
    assert transition.json()["code"] == "credential-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        ticket = connection.execute(
            "SELECT project_key, custodian_principal_id, version FROM tickets WHERE ticket_id = %s",
            (UUID(created.json()["ticket"]["ticket_id"]),),
        ).fetchone()
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM seat_credential_issuances) AS issuances,
                (SELECT count(*) FROM events
                 WHERE kind = 'access.seat_credential_issued') AS issuance_events
            """
        ).fetchone()
    assert ticket == {
        "project_key": "manibo",
        "custodian_principal_id": UUID(receipt["principal_id"]),
        "version": 1,
    }
    assert facts == {"issuances": 1, "issuance_events": 1}


def test_issuance_is_operator_only_and_owner_is_not_a_grantable_scope(
    tenant: TenantFixture,
) -> None:
    with _client(tenant) as client:
        commander_attempt = _issue(
            client,
            tenant.commander_credential,
            command_id=uuid4(),
            credential=secrets.token_urlsafe(32),
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture",),
        )
        owner_scope = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=secrets.token_urlsafe(32),
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("owner",),
        )

    assert commander_attempt.status_code == HTTP_FORBIDDEN
    assert commander_attempt.json()["code"] == "credential-issuance-refused"
    assert owner_scope.status_code == HTTP_UNPROCESSABLE
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM seat_credential_issuances").fetchone()
    assert count == (0,)


def test_revocation_appends_and_the_next_call_refuses_by_name(
    tenant: TenantFixture,
) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("capture", "transition", "evidence"),
        )
        credential_id = UUID(issued.json()["credential_id"])
        revoked = cast(
            Response,
            client.post(
                f"/v1/admin/seat-credentials/{credential_id}/revocation",
                json={"reason": "Seat rotation"},
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )
        next_call = cast(
            Response,
            client.get(f"/v1/tickets/{uuid4()}", headers=_auth(credential)),
        )

    assert issued.status_code == HTTP_PENDING
    assert revoked.status_code == HTTP_PENDING
    assert revoked.json()["state"] == "revoked"
    assert next_call.status_code == HTTP_UNAUTHORIZED
    assert next_call.json()["code"] == "credential-revoked"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        events = connection.execute(
            """
            SELECT kind, payload FROM events
            WHERE aggregate_id = %s ORDER BY sequence
            """,
            (credential_id,),
        ).fetchall()
        revocations = connection.execute(
            """
            SELECT count(*) AS revocations FROM seat_credential_revocations
            WHERE credential_id = %s
            """,
            (credential_id,),
        ).fetchone()
    assert [row["kind"] for row in events] == [
        "access.seat_credential_issued",
        "access.seat_credential_revoked",
    ]
    serialized = json.dumps([row["payload"] for row in events], sort_keys=True)
    assert credential not in serialized
    assert hashlib.sha256(credential.encode()).hexdigest() not in serialized
    assert revocations == {"revocations": 1}


def test_manibo_seat_cannot_mutate_ctower_ticket_by_name(tenant: TenantFixture) -> None:
    credential = secrets.token_urlsafe(32)
    with _client(tenant) as client:
        ctower = cast(
            Response,
            client.post(
                "/v1/tickets",
                json={
                    "initial_custodian_id": str(tenant.commander_id),
                    "priority": "P2",
                    "source": {"kind": "mission-control", "ref": "ctower-R192"},
                    "title": "Ctower-owned ticket",
                },
                headers={
                    **_auth(tenant.operator_credential),
                    "Idempotency-Key": str(uuid4()),
                },
            ),
        )
        issued = _issue(
            client,
            tenant.operator_credential,
            command_id=uuid4(),
            credential=credential,
            project_key="manibo",
            seat_key="manibo-commander",
            scopes=("transition",),
        )
        ticket_id = UUID(ctower.json()["ticket"]["ticket_id"])
        refused = cast(
            Response,
            client.post(
                f"/v1/tickets/{ticket_id}/priority",
                json={
                    "expected_version": 1,
                    "priority": "P1",
                    "reason": "Foreign mutation probe",
                },
                headers={**_auth(credential), "Idempotency-Key": str(uuid4())},
            ),
        )

    assert ctower.status_code == HTTP_PENDING
    assert issued.status_code == HTTP_PENDING
    assert refused.status_code == HTTP_FORBIDDEN
    assert refused.json()["code"] == "project-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        fingerprint = connection.execute(
            """
            SELECT ticket.project_key, ticket.version,
                (SELECT count(*) FROM events
                 WHERE aggregate_id = ticket.ticket_id AND kind = 'work.changed')
            FROM tickets AS ticket WHERE ticket.ticket_id = %s
            """,
            (ticket_id,),
        ).fetchone()
    assert fingerprint == ("ctower", 1, 0)


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )


def _issue(
    client: TestClient,
    authority: str,
    *,
    command_id: UUID,
    credential: str,
    project_key: str,
    seat_key: str,
    scopes: tuple[str, ...],
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/admin/seat-credentials",
            json={
                "credential_digest": (f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}"),
                "credential_ref": f"secret-ref:test/{project_key}/{seat_key}",
                "display_name": f"{project_key.title()} Commander",
                "project_key": project_key,
                "scopes": list(scopes),
                "seat_key": seat_key,
            },
            headers={**_auth(authority), "Idempotency-Key": str(command_id)},
        ),
    )


def _auth(credential: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(),
    }
