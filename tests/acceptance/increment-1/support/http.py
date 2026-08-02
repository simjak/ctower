"""Authenticated acceptance-test HTTP composition."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ctower_contracts import CATALOG
from fastapi import FastAPI
from support.catalog import MemoryObjectStore
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import PostgresCatalog
from ctower_kernel.record.postgres import PostgresRecord

__all__ = ["app_for", "operator_headers"]


def app_for(
    tenant: TenantFixture,
    *,
    store: MemoryObjectStore | None = None,
) -> FastAPI:
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        CATALOG,
        store or MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )
    return create_app(PostgresRecord(tenant.database.runtime_dsn), catalog=catalog)


def operator_headers(
    tenant: TenantFixture,
    *,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        **telemetry_headers(),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers
