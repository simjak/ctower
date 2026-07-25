"""Exact run-scoped migration-importer credential resolution."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_client.models import CtowerProjectImportRunCreateRequest
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()


def create_binding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    run_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    """Create the digest-only principal and its first immutable lifecycle fact."""

    _create_principal_credential(
        connection,
        actor,
        request,
        run_id=run_id,
        principal_id=principal_id,
        now=now,
    )
    _create_run_binding(
        connection,
        actor,
        request,
        run_id=run_id,
        principal_id=principal_id,
        now=now,
    )
    connection.execute(
        """
        INSERT INTO migration_importer_credential_facts (
            credential_fact_id, run_id, principal_id, fact_sequence, lifecycle,
            actor_principal_id, command_id, recorded_at
        ) VALUES (%s, %s, %s, 1, 'activated', %s, %s, %s)
        """,
        (_uuid7(now), run_id, principal_id, actor.principal_id, command_id, now),
    )


def _create_principal_credential(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    run_id: UUID,
    principal_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled, created_at
        ) VALUES (%s, %s, 'migration_importer', %s, false, %s)
        """,
        (principal_id, actor.tenant_id, f"ctower:migration-importer:{run_id}", now),
    )
    connection.execute(
        """
        INSERT INTO principal_credentials (
            credential_id, principal_id, tenant_id, credential_digest, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            _uuid7(now),
            principal_id,
            actor.tenant_id,
            _digest_bytes(request.importer_credential_digest),
            now,
        ),
    )


def _create_run_binding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportRunCreateRequest,
    *,
    run_id: UUID,
    principal_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_importer_bindings (
            run_id, tenant_id, cutover_id, project_key, principal_id,
            credential_digest, expires_at, created_at
        ) VALUES (%s, %s, %s, 'ctower', %s, %s, %s, %s)
        """,
        (
            run_id,
            actor.tenant_id,
            request.cutover_id,
            principal_id,
            _digest_bytes(request.importer_credential_digest),
            request.importer_expires_at,
            now,
        ),
    )


def resolve_importer(
    dsn: str,
    credential_digest: bytes,
    run_id: UUID,
    cutover_id: UUID,
    project_key: str,
    *,
    now: datetime,
) -> Actor | None:
    """Resolve only the active digest for one exact run/cutover/project tuple."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT binding.principal_id, binding.tenant_id
            FROM migration_importer_bindings AS binding
            JOIN principals AS principal
              ON principal.principal_id = binding.principal_id
             AND principal.tenant_id = binding.tenant_id
            JOIN LATERAL (
                SELECT lifecycle FROM migration_importer_credential_facts
                WHERE run_id = binding.run_id ORDER BY fact_sequence DESC LIMIT 1
            ) AS fact ON true
            WHERE binding.credential_digest = %s
              AND binding.run_id = %s AND binding.cutover_id = %s
              AND binding.project_key = %s AND binding.expires_at > %s
              AND fact.lifecycle = 'activated' AND NOT principal.disabled
              AND principal.kind = 'migration_importer'
            """,
            (credential_digest, run_id, cutover_id, project_key, now),
        ).fetchone()
    if row is None:
        return None
    return Actor(
        cast(UUID, row["principal_id"]),
        cast(UUID, row["tenant_id"]),
        PrincipalKind.MIGRATION_IMPORTER,
    )


def resolve_fence_observer(
    dsn: str,
    credential_digest: bytes,
    *,
    now: datetime,
) -> Actor | None:
    """Resolve a credential that can only append degrading fence observations."""

    del now
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT principal.principal_id, principal.tenant_id
            FROM principal_credentials AS credential
            JOIN principals AS principal
              ON principal.principal_id = credential.principal_id
             AND principal.tenant_id = credential.tenant_id
            WHERE credential.credential_digest = %s
              AND credential.revoked_at IS NULL AND NOT principal.disabled
              AND principal.kind = 'fence_observer'
            """,
            (credential_digest,),
        ).fetchone()
    if row is None:
        return None
    return Actor(
        cast(UUID, row["principal_id"]),
        cast(UUID, row["tenant_id"]),
        PrincipalKind.FENCE_OBSERVER,
    )


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
