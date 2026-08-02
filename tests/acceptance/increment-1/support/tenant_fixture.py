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
from support.telemetry import telemetry_headers

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import (
    PostgresRecord,
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)

__all__ = [
    "TenantFixture",
    "create_first_tenant",
    "create_second_tenant",
    "provision_credential",
]

HTTP_PENDING = 202


@dataclass(frozen=True, slots=True)
class TenantFixture:
    """One real tenant with operator and Commander bearer credentials."""

    database: DatabaseFixture
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID
    operator_credential: str
    commander_credential: str


def create_first_tenant(
    database: DatabaseFixture,
    *,
    commander_name: str = "Ctower Commander",
    operator_name: str = "First Operator",
) -> TenantFixture:
    """Execute bootstrap, then bind runtime fixture credentials by digest."""

    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    bootstrap_token = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.migrator_dsn,
        capability_input=io.StringIO(f"{bootstrap_token}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with TestClient(
        create_app(PostgresRecord(database.runtime_dsn)), client=("127.0.0.1", 51000)
    ) as client:
        response = _bootstrap(
            client,
            bootstrap_token,
            commander_name=commander_name,
            operator_name=operator_name,
        )
    if response.status_code != HTTP_PENDING:
        raise RuntimeError(f"first-tenant fixture bootstrap failed: {response.status_code}")
    payload = response.json()
    tenant_id = UUID(str(payload["tenant_id"]))
    operator_id = UUID(str(payload["operator_id"]))
    commander_id = UUID(str(payload["commander_id"]))
    operator_credential = secrets.token_urlsafe(32)
    commander_credential = secrets.token_urlsafe(32)
    provision_credential(database.admin_dsn, tenant_id, operator_id, operator_credential)
    provision_credential(database.admin_dsn, tenant_id, commander_id, commander_credential)
    return TenantFixture(
        database,
        tenant_id,
        operator_id,
        commander_id,
        operator_credential,
        commander_credential,
    )


def create_second_tenant(database: DatabaseFixture) -> TenantFixture:
    """Provision a real isolated tenant through setup-only administrator authority."""

    now = datetime.now(UTC)
    tenant_id, operator_id, commander_id = (_uuid7(now) for _ in range(3))
    operator_credential = secrets.token_urlsafe(32)
    commander_credential = secrets.token_urlsafe(32)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
            (tenant_id, "tenant-two", "Tenant Two", now),
        )
        connection.cursor().executemany(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, %s, %s, false, %s, %s, %s)
            """,
            (
                (
                    operator_id,
                    tenant_id,
                    "operator",
                    "Tenant Two Operator",
                    "credential-ref:tenant-two/operator",
                    "vault-ref:tenant-two/operator",
                    now,
                ),
                (
                    commander_id,
                    tenant_id,
                    "commander",
                    "Tenant Two Commander",
                    None,
                    "vault-ref:tenant-two/commander",
                    now,
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, 'ctower', 'ctower-commander', %s, %s)
            """,
            (commander_id, tenant_id, operator_id, now),
        )
    provision_credential(database.admin_dsn, tenant_id, operator_id, operator_credential)
    provision_credential(database.admin_dsn, tenant_id, commander_id, commander_credential)
    return TenantFixture(
        database,
        tenant_id,
        operator_id,
        commander_id,
        operator_credential,
        commander_credential,
    )


def _bootstrap(
    client: TestClient,
    token: str,
    *,
    commander_name: str,
    operator_name: str,
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/bootstrap/first-tenant",
            json={
                "commander_name": commander_name,
                "commander_vault_ref": "vault-ref:ctower/commander",
                "operator_credential_ref": "credential-ref:ctower/operator",
                "operator_name": operator_name,
                "operator_vault_ref": "vault-ref:ctower/operator",
                "tenant_name": "Ctower",
                "tenant_slug": "ctower",
            },
            headers={
                **telemetry_headers(command_id),
                "Idempotency-Key": str(command_id),
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
                _uuid7(datetime.now(UTC)),
                principal_id,
                tenant_id,
                hashlib.sha256(credential.encode()).digest(),
                datetime.now(UTC),
            ),
        )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
