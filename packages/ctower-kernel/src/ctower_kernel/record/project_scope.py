"""The persisted Project authority one principal holds inside one tenant."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

__all__ = ["project_scope_grants"]


def project_scope_grants(
    connection: psycopg.Connection[dict[str, object]],
    *,
    tenant_id: UUID,
    principal_id: UUID,
) -> tuple[str, ...]:
    """Every Project key this principal reaches, so a read can bind its answer to it.

    The refusal below answers whether named Projects are inside the grant; a read
    that names none has to bind its rows to the grant itself, and deriving that
    grant anywhere else would let a second authority disagree with the chokepoint
    about the same principal. Unrestricted operator authority reaches every Project
    the tenant registered a seat in, so a caller never branches on authority kind.
    """

    principal = _scope_principal(connection, tenant_id, principal_id)
    human_grants = _human_project_grants(principal)
    if _operator_scope_allowed(principal, human_grants, allow_operator_read=True):
        return _tenant_project_keys(connection, tenant_id)
    seat_grants = _seat_project_grants(connection, tenant_id, principal_id)
    return tuple(sorted((human_grants or set()) | seat_grants))


def _scope_principal(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, principal_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT principal.kind, principal.disabled,
               binding.project_keys AS human_project_keys
        FROM principals AS principal
        LEFT JOIN human_role_bindings AS binding
          ON binding.tenant_id = principal.tenant_id
         AND binding.principal_id = principal.principal_id
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.tenant_id = binding.tenant_id
         AND revocation.binding_id = binding.binding_id
        WHERE principal.tenant_id = %s AND principal.principal_id = %s
          AND (binding.binding_id IS NULL OR revocation.binding_id IS NULL)
        ORDER BY binding.granted_at DESC NULLS LAST
        LIMIT 1
        """,
        (tenant_id, principal_id),
    ).fetchone()


def _human_project_grants(principal: dict[str, object] | None) -> set[str] | None:
    return (
        set(cast(list[str], principal["human_project_keys"]))
        if principal is not None and principal["human_project_keys"] is not None
        else None
    )


def _operator_scope_allowed(
    principal: dict[str, object] | None,
    human_grants: set[str] | None,
    *,
    allow_operator_read: bool,
) -> bool:
    return (
        principal is not None
        and principal["kind"] == "operator"
        and (allow_operator_read or human_grants is None)
    )


def _seat_project_grants(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, principal_id: UUID
) -> set[str]:
    return {
        str(row["project_key"])
        for row in connection.execute(
            """
            SELECT project_key
            FROM project_seats
            WHERE tenant_id = %s AND principal_id = %s
            """,
            (tenant_id, principal_id),
        ).fetchall()
    }


def _tenant_project_keys(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(row["project_key"])
            for row in connection.execute(
                """
                SELECT DISTINCT project_key
                FROM project_seats
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            ).fetchall()
        )
    )
