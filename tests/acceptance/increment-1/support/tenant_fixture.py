"""Real authenticated first-tenant fixture for Increment-1 acceptance."""

from __future__ import annotations

import hashlib
import io
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from support.postgres import DatabaseFixture

from ctower_api.interface import create_app
from ctower_api.postgres import PostgresRecord, apply_migrations, provision_bootstrap

__all__ = ["TenantFixture", "create_first_tenant", "provision_credential"]

HTTP_CREATED = 201


@dataclass(frozen=True, slots=True)
class TenantFixture:
    """One real tenant with operator and Commander bearer credentials."""

    database: DatabaseFixture
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID
    operator_credential: str
    commander_credential: str


def create_first_tenant(database: DatabaseFixture) -> TenantFixture:
    """Execute bootstrap, then bind runtime fixture credentials by digest."""

    apply_migrations(database.dsn)
    bootstrap_token = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.dsn,
        capability_input=io.StringIO(f"{bootstrap_token}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with TestClient(
        create_app(PostgresRecord(database.dsn)), client=("127.0.0.1", 51000)
    ) as client:
        response = _bootstrap(client, bootstrap_token)
    if response.status_code != HTTP_CREATED:
        raise RuntimeError(f"first-tenant fixture bootstrap failed: {response.status_code}")
    payload = response.json()
    tenant_id = UUID(str(payload["tenant_id"]))
    operator_id = UUID(str(payload["operator_id"]))
    commander_id = UUID(str(payload["commander_id"]))
    operator_credential = secrets.token_urlsafe(32)
    commander_credential = secrets.token_urlsafe(32)
    provision_credential(database.dsn, tenant_id, operator_id, operator_credential)
    provision_credential(database.dsn, tenant_id, commander_id, commander_credential)
    return TenantFixture(
        database,
        tenant_id,
        operator_id,
        commander_id,
        operator_credential,
        commander_credential,
    )


def _bootstrap(client: TestClient, token: str) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/bootstrap/first-tenant",
            json={
                "commander_name": "Ctower Commander",
                "commander_vault_ref": "vault-ref:ctower/commander",
                "operator_credential_ref": "credential-ref:ctower/operator",
                "operator_name": "First Operator",
                "operator_vault_ref": "vault-ref:ctower/operator",
                "tenant_name": "Ctower",
                "tenant_slug": "ctower",
            },
            headers={
                "Idempotency-Key": str(uuid4()),
                "X-Ctower-Bootstrap-Capability": token,
            },
        ),
    )


def provision_credential(dsn: str, tenant_id: UUID, principal_id: UUID, credential: str) -> None:
    """Bind only a digest for a runtime acceptance credential."""

    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            INSERT INTO principal_credentials (
                credential_id, principal_id, tenant_id, credential_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                principal_id,
                tenant_id,
                hashlib.sha256(credential.encode()).digest(),
                datetime.now(UTC),
            ),
        )
