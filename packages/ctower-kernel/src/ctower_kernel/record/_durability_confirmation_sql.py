"""Immutable proof that a finalization was read from its named standby."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg

from ctower_kernel.record._command_root import CommandSnapshot
from ctower_kernel.record._durability_evidence import Finalization, Receipt
from ctower_kernel.record.transaction import authority_connection

__all__: tuple[str, ...] = ()


class _CommandIdentity(Protocol):
    @property
    def tenant_id(self) -> UUID: ...

    @property
    def principal_id(self) -> UUID: ...

    @property
    def command_id(self) -> UUID: ...


def acceptance_finalization(
    connection: psycopg.Connection[dict[str, object]], identity: _CommandIdentity
) -> Finalization | None:
    """Load one immutable acceptance finalization by complete command identity."""

    row = connection.execute(
        """
        SELECT tenant_id, principal_id, client_command_id, request_sha256,
            command_root, acceptance_position, policy_ref, standby_application_name,
            standby_identity, standby_system_identifier, standby_timeline_id,
            standby_replay_lsn::text AS standby_replay_lsn
        FROM durability_acceptance_finalizations
        WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
        """,
        (identity.tenant_id, identity.principal_id, identity.command_id),
    ).fetchone()
    if row is None:
        return None
    return _from_row(row)


def confirmation(
    connection: psycopg.Connection[dict[str, object]], identity: _CommandIdentity
) -> Finalization | None:
    """Load the exact locally durable named-standby observation, if one exists."""

    row = connection.execute(
        """
        SELECT tenant_id, principal_id, client_command_id, request_sha256,
            command_root, acceptance_position, policy_ref, standby_application_name,
            standby_identity, standby_system_identifier, standby_timeline_id,
            standby_replay_lsn::text AS standby_replay_lsn
        FROM durability_acceptance_confirmations
        WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
        """,
        (identity.tenant_id, identity.principal_id, identity.command_id),
    ).fetchone()
    if row is None:
        return None
    return _from_row(row)


def insert_finalization(
    connection: psycopg.Connection[dict[str, object]],
    snapshot: CommandSnapshot,
    receipt: Receipt,
    *,
    now: datetime,
) -> None:
    """Insert one finalization bound field-for-field to its acknowledgement."""

    connection.execute(
        """
        INSERT INTO durability_acceptance_finalizations (
            tenant_id, principal_id, client_command_id, request_sha256,
            command_root, acceptance_position, policy_ref,
            standby_application_name, standby_identity,
            standby_system_identifier, standby_timeline_id,
            standby_replay_lsn, finalized_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, principal_id, client_command_id) DO NOTHING
        """,
        (
            snapshot.tenant_id,
            snapshot.principal_id,
            snapshot.command_id,
            receipt.request_digest,
            receipt.command_root,
            receipt.acceptance_position,
            receipt.policy_ref,
            receipt.standby_application_name,
            receipt.standby_identity,
            receipt.standby_system_identifier,
            receipt.standby_timeline_id,
            receipt.standby_replay_lsn,
            now,
        ),
    )


def store_confirmation(primary_dsn: str, finalization: Finalization, *, now: datetime) -> bool:
    """Persist a local observation only after the caller read the named standby."""

    try:
        with _service_connection(primary_dsn) as primary:
            primary.execute("SET LOCAL synchronous_commit = local")
            primary.execute(
                """
                INSERT INTO durability_acceptance_confirmations (
                    tenant_id, principal_id, client_command_id, request_sha256,
                    command_root, acceptance_position, policy_ref,
                    standby_application_name, standby_identity,
                    standby_system_identifier, standby_timeline_id,
                    standby_replay_lsn, confirmed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, principal_id, client_command_id) DO NOTHING
                """,
                (*_values(finalization), now),
            )
        with _service_connection(primary_dsn) as primary:
            stored = confirmation(primary, finalization)
    except psycopg.Error:
        return False
    return stored == finalization


def current_copy_is_named_standby(
    connection: psycopg.Connection[dict[str, object]], receipt: Receipt
) -> bool:
    """Recognize a promoted named copy without relying on a primary-local confirmation."""

    row = connection.execute(
        """
        SELECT current_setting('cluster_name') AS cluster_name,
            (pg_control_system()).system_identifier AS system_identifier,
            (pg_control_checkpoint()).timeline_id AS timeline_id
        """
    ).fetchone()
    return bool(
        row is not None
        and str(row["cluster_name"]) == receipt.standby_identity
        and int(str(row["system_identifier"])) == receipt.standby_system_identifier
        and int(cast(int, row["timeline_id"])) >= receipt.standby_timeline_id
    )


def _service_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    connection = authority_connection(dsn)
    connection.execute("SET ROLE ctower_svc")
    return connection


def _values(value: Finalization) -> tuple[object, ...]:
    return (
        value.tenant_id,
        value.principal_id,
        value.command_id,
        value.request_digest,
        value.command_root,
        value.acceptance_position,
        value.policy_ref,
        value.standby_application_name,
        value.standby_identity,
        value.standby_system_identifier,
        value.standby_timeline_id,
        value.standby_replay_lsn,
    )


def _from_row(row: dict[str, object]) -> Finalization:
    return Finalization(
        cast(UUID, row["tenant_id"]),
        cast(UUID, row["principal_id"]),
        cast(UUID, row["client_command_id"]),
        bytes(cast(bytes, row["request_sha256"])),
        bytes(cast(bytes, row["command_root"])),
        int(cast(int, row["acceptance_position"])),
        str(row["policy_ref"]),
        str(row["standby_application_name"]),
        str(row["standby_identity"]),
        int(str(row["standby_system_identifier"])),
        int(cast(int, row["standby_timeline_id"])),
        str(row["standby_replay_lsn"]),
    )
