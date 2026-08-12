"""Shared data-layer guard queries for terminal Routine retirement."""

from __future__ import annotations

from uuid import UUID

import psycopg

__all__: tuple[str, ...] = ()


def lock_routine_tenant(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> None:
    tenant = connection.execute(
        "SELECT tenant_id FROM tenants WHERE tenant_id = %s FOR UPDATE", (tenant_id,)
    ).fetchone()
    if tenant is None:
        raise ValueError("Routine tenant does not exist")


def routine_is_retired(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, routine_ref: str
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM routine_retirements
        WHERE tenant_id = %s AND routine_ref = %s
        """,
        (tenant_id, routine_ref),
    ).fetchone()
    return row is not None
