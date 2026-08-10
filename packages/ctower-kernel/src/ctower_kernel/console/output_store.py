"""Encrypted Console output persistence behind its dedicated reader role."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.console.models import (
    ConsoleCiphertext,
    ConsoleStreamLease,
    StoredConsoleOutput,
)
from ctower_kernel.record.identifiers import uuid7

__all__ = ["PostgresConsoleOutputStore"]


class PostgresConsoleOutputStore:
    """Persist ciphertext and read it only through the custody reader role."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def latest_source_cursor(self, allowance_id: UUID, tenant_id: UUID) -> int:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(max(source_cursor), 0) AS cursor
                FROM console_output_objects
                WHERE allowance_id = %s AND tenant_id = %s
                """,
                (allowance_id, tenant_id),
            ).fetchone()
        return cast(int, row["cursor"]) if row is not None else 0

    def latest_durable_cursor(self, allowance_id: UUID, tenant_id: UUID) -> int:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(max(cursor), 0) AS cursor
                FROM console_output_objects
                WHERE allowance_id = %s AND tenant_id = %s
                """,
                (allowance_id, tenant_id),
            ).fetchone()
        return cast(int, row["cursor"]) if row is not None else 0

    def append_output(
        self,
        allowance_id: UUID,
        tenant_id: UUID,
        source_cursor: int,
        envelope: ConsoleCiphertext,
        *,
        object_sha256: bytes,
        decoded_bytes: int,
        now: datetime,
    ) -> int:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                INSERT INTO console_output_objects (
                    object_id, tenant_id, allowance_id, source_cursor, ciphertext,
                    content_nonce, wrapped_data_key, wrapping_nonce,
                    wrapping_key_reference, data_key_reference, object_sha256,
                    decoded_bytes, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING cursor
                """,
                (
                    envelope.object_id,
                    tenant_id,
                    allowance_id,
                    source_cursor,
                    envelope.ciphertext,
                    envelope.content_nonce,
                    envelope.wrapped_data_key,
                    envelope.wrapping_nonce,
                    envelope.wrapping_key_reference,
                    envelope.data_key_reference,
                    object_sha256,
                    decoded_bytes,
                    now,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("console output insert returned no cursor")
        return cast(int, row["cursor"])

    def outputs_after(
        self, allowance_id: UUID, tenant_id: UUID, cursor: int, *, limit: int = 64
    ) -> tuple[StoredConsoleOutput, ...]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE console_output_reader")
            rows = connection.execute(
                """
                SELECT * FROM console_output_objects
                WHERE allowance_id = %s AND tenant_id = %s AND cursor > %s
                ORDER BY cursor LIMIT %s
                """,
                (allowance_id, tenant_id, cursor, limit),
            ).fetchall()
        return tuple(_stored_output(row) for row in rows)

    def record_output_access(
        self,
        lease: ConsoleStreamLease,
        output: StoredConsoleOutput,
        access_kind: Literal["open", "reconnect", "replay", "forensic"],
        *,
        now: datetime,
    ) -> None:
        with _authority_connection(self._dsn) as connection:
            connection.execute(
                """
                INSERT INTO console_output_access_facts (
                    access_id, tenant_id, object_id, grant_id, stream_id,
                    access_kind, accessed_by, accessed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid7(now),
                    lease.grant.tenant_id,
                    output.envelope.object_id,
                    lease.grant.grant_id,
                    lease.stream_id,
                    access_kind,
                    lease.grant.actor_principal_id,
                    now,
                ),
            )

    def record_gap(
        self,
        allowance_id: UUID,
        tenant_id: UUID,
        source_cursor: int,
        reason: Literal[
            "cursor_unavailable",
            "source_truncated",
            "unprovable_range",
            "slow_consumer",
            "rate_limited",
        ],
        *,
        now: datetime,
    ) -> None:
        with _authority_connection(self._dsn) as connection:
            connection.execute(
                """
                INSERT INTO console_output_gap_facts (
                    gap_id, tenant_id, allowance_id, source_cursor, reason, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uuid7(now), tenant_id, allowance_id, source_cursor, reason, now),
            )


def _authority_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    connection = psycopg.connect(dsn, row_factory=dict_row)
    connection.execute("SET ROLE ctower_svc")
    return connection


def _stored_output(row: dict[str, object]) -> StoredConsoleOutput:
    return StoredConsoleOutput(
        cursor=cast(int, row["cursor"]),
        source_cursor=cast(int, row["source_cursor"]),
        decoded_bytes=cast(int, row["decoded_bytes"]),
        object_sha256=bytes(cast(bytes, row["object_sha256"])),
        envelope=ConsoleCiphertext(
            object_id=cast(UUID, row["object_id"]),
            ciphertext=bytes(cast(bytes, row["ciphertext"])),
            content_nonce=bytes(cast(bytes, row["content_nonce"])),
            wrapped_data_key=bytes(cast(bytes, row["wrapped_data_key"])),
            wrapping_nonce=bytes(cast(bytes, row["wrapping_nonce"])),
            wrapping_key_reference=str(row["wrapping_key_reference"]),
            data_key_reference=cast(UUID, row["data_key_reference"]),
        ),
    )
