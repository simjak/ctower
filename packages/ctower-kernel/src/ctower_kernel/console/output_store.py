"""Encrypted Console output persistence behind its dedicated reader role."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.console.models import (
    ConsoleCiphertext,
    ConsoleStreamLease,
    StoredConsoleGap,
    StoredConsoleOutput,
    StreamCloseCode,
)
from ctower_kernel.record import RecordProblem
from ctower_kernel.record.identifiers import uuid7

__all__ = ["PostgresConsoleOutputStore"]


class PostgresConsoleOutputStore:
    """Persist ciphertext and read it only through the custody reader role."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def latest_source_position(self, allowance_id: UUID, tenant_id: UUID) -> tuple[int, int]:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT source_cursor, source_generation
                FROM (
                    SELECT source_cursor, source_generation, source_position
                    FROM console_output_objects
                    WHERE allowance_id = %s AND tenant_id = %s
                    UNION ALL
                    SELECT source_cursor, source_generation, source_position
                    FROM console_output_gap_facts
                    WHERE allowance_id = %s AND tenant_id = %s
                      AND advances_source_position
                ) AS positions
                ORDER BY source_position DESC LIMIT 1
                """,
                (allowance_id, tenant_id, allowance_id, tenant_id),
            ).fetchone()
        if row is None:
            return 0, 1
        return cast(int, row["source_cursor"]), cast(int, row["source_generation"])

    def latest_durable_cursor(self, allowance_id: UUID, tenant_id: UUID) -> int:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(max(cursor), 0) AS cursor
                FROM (
                    SELECT cursor FROM console_output_objects
                    WHERE allowance_id = %s AND tenant_id = %s
                    UNION ALL
                    SELECT cursor FROM console_output_gap_facts
                    WHERE allowance_id = %s AND tenant_id = %s
                ) AS durable_events
                """,
                (allowance_id, tenant_id, allowance_id, tenant_id),
            ).fetchone()
        return cast(int, row["cursor"]) if row is not None else 0

    def append_output_locked(
        self,
        connection: psycopg.Connection[dict[str, object]],
        allowance_id: UUID,
        tenant_id: UUID,
        source_cursor: int,
        source_generation: int,
        envelope: ConsoleCiphertext,
        *,
        object_sha256: bytes,
        decoded_bytes: int,
        now: datetime,
    ) -> int:
        row = connection.execute(
            """
            INSERT INTO console_output_objects (
                object_id, tenant_id, allowance_id, source_cursor, source_generation,
                ciphertext,
                content_nonce, wrapped_data_key, wrapping_nonce,
                wrapping_key_reference, data_key_reference, object_sha256,
                decoded_bytes, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING cursor
            """,
            (
                envelope.object_id,
                tenant_id,
                allowance_id,
                source_cursor,
                source_generation,
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

    @contextmanager
    def collection_lock(
        self, allowance_id: UUID, tenant_id: UUID
    ) -> Iterator[psycopg.Connection[dict[str, object]]]:
        """Serialize Adapter collection for one exact allowed session across processes."""

        with _authority_connection(self._dsn) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"console-collection:{tenant_id}:{allowance_id}",),
            )
            yield connection

    def owns_cursor(self, allowance_id: UUID, tenant_id: UUID, cursor: int) -> bool:
        if cursor == 0:
            return True
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM (
                    SELECT cursor FROM console_output_objects
                    WHERE allowance_id = %s AND tenant_id = %s
                    UNION ALL
                    SELECT cursor FROM console_output_gap_facts
                    WHERE allowance_id = %s AND tenant_id = %s
                ) AS durable_events
                WHERE cursor = %s
                """,
                (allowance_id, tenant_id, allowance_id, tenant_id, cursor),
            ).fetchone()
        return row is not None

    def outputs_after(
        self,
        lease: ConsoleStreamLease,
        cursor: int,
        access_kind: Literal["open", "reconnect", "replay", "forensic"],
        *,
        authorize: Callable[[psycopg.Connection[dict[str, object]]], StreamCloseCode | None],
        now: datetime,
        limit: int = 1,
    ) -> tuple[StoredConsoleOutput | StoredConsoleGap, ...] | RecordProblem | StreamCloseCode:
        """Lock authority and record recovery access before the custody-role SELECT."""

        try:
            authorized: list[tuple[dict[str, object], UUID | None]] = []
            with _authority_connection(self._dsn) as connection:
                close_code = authorize(connection)
                if close_code is not None:
                    return close_code
                metadata = connection.execute(
                    """
                    SELECT cursor, object_id, NULL::bigint AS source_cursor,
                           NULL::bigint AS source_generation, NULL::text AS reason
                    FROM console_output_objects
                    WHERE allowance_id = %s AND tenant_id = %s AND cursor > %s
                    UNION ALL
                    SELECT cursor, NULL::uuid AS object_id, source_cursor,
                           source_generation, reason
                    FROM console_output_gap_facts
                    WHERE allowance_id = %s AND tenant_id = %s AND cursor > %s
                    ORDER BY cursor LIMIT %s
                    """,
                    (
                        lease.grant.allowance_id,
                        lease.grant.tenant_id,
                        cursor,
                        lease.grant.allowance_id,
                        lease.grant.tenant_id,
                        cursor,
                        limit,
                    ),
                ).fetchall()
                for row in metadata:
                    object_id = cast(UUID | None, row["object_id"])
                    access_id = None if object_id is None else uuid7(now)
                    if access_id is not None and object_id is not None:
                        self._record_access_locked(
                            connection,
                            access_id,
                            lease,
                            object_id,
                            access_kind,
                            now=now,
                        )
                    authorized.append((row, access_id))
            events = [self._recover_event(row, access_id, now=now) for row, access_id in authorized]
        except psycopg.Error:
            return RecordProblem(
                code="console-output-unavailable",
                detail="The authorized Console output custody path is unavailable.",
                status=503,
                title="Console output unavailable",
            )
        return tuple(events)

    def _recover_event(
        self,
        row: dict[str, object],
        access_id: UUID | None,
        *,
        now: datetime,
    ) -> StoredConsoleOutput | StoredConsoleGap:
        if access_id is None:
            return _stored_gap(row)
        recovered = self._recover_object(access_id, now=now)
        if recovered is None:
            raise RuntimeError("authorized Console output object disappeared")
        return _stored_output(recovered)

    def _record_access_locked(
        self,
        connection: psycopg.Connection[dict[str, object]],
        access_id: UUID,
        lease: ConsoleStreamLease,
        object_id: UUID,
        access_kind: Literal["open", "reconnect", "replay", "forensic"],
        *,
        now: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO console_output_access_facts (
                access_id, tenant_id, object_id, grant_id, stream_id,
                access_kind, outcome, accessed_by, accessed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'authorized', %s, %s)
            """,
            (
                access_id,
                lease.grant.tenant_id,
                object_id,
                lease.grant.grant_id,
                lease.stream_id,
                access_kind,
                lease.grant.actor_principal_id,
                now,
            ),
        )

    def _recover_object(self, access_id: UUID, *, now: datetime) -> dict[str, object] | None:
        with _authority_connection(self._dsn) as connection:
            return connection.execute(
                """
                SELECT * FROM recover_console_output_object(%s, %s)
                """,
                (access_id, now),
            ).fetchone()

    def record_gap(
        self,
        allowance_id: UUID,
        tenant_id: UUID,
        source_cursor: int,
        source_generation: int,
        reason: Literal[
            "cursor_unavailable",
            "source_truncated",
            "unprovable_range",
            "slow_consumer",
            "rate_limited",
        ],
        *,
        advances_source_position: bool,
        now: datetime,
    ) -> int:
        with self.collection_lock(allowance_id, tenant_id) as connection:
            return self.record_gap_locked(
                connection,
                allowance_id,
                tenant_id,
                source_cursor=source_cursor,
                source_generation=source_generation,
                reason=reason,
                advances_source_position=advances_source_position,
                now=now,
            )

    def record_gap_locked(
        self,
        connection: psycopg.Connection[dict[str, object]],
        allowance_id: UUID,
        tenant_id: UUID,
        *,
        source_cursor: int,
        source_generation: int,
        reason: Literal[
            "cursor_unavailable",
            "source_truncated",
            "unprovable_range",
            "slow_consumer",
            "rate_limited",
        ],
        advances_source_position: bool,
        now: datetime,
    ) -> int:
        """Insert one gap while the caller holds the per-allowance collection lock."""

        row = connection.execute(
            """
            INSERT INTO console_output_gap_facts (
                gap_id, tenant_id, allowance_id, source_cursor,
                source_generation, advances_source_position, reason, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING cursor
            """,
            (
                uuid7(now),
                tenant_id,
                allowance_id,
                source_cursor,
                source_generation,
                advances_source_position,
                reason,
                now,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("console output gap insert returned no cursor")
        return cast(int, row["cursor"])


def _authority_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    connection = psycopg.connect(dsn, row_factory=dict_row)
    connection.execute("SET ROLE ctower_svc")
    return connection


def _stored_output(row: dict[str, object]) -> StoredConsoleOutput:
    return StoredConsoleOutput(
        cursor=cast(int, row["cursor"]),
        source_cursor=cast(int, row["source_cursor"]),
        source_generation=cast(int, row["source_generation"]),
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


def _stored_gap(row: dict[str, object]) -> StoredConsoleGap:
    return StoredConsoleGap(
        cursor=cast(int, row["cursor"]),
        source_cursor=cast(int, row["source_cursor"]),
        source_generation=cast(int, row["source_generation"]),
        reason=cast(
            Literal[
                "cursor_unavailable",
                "source_truncated",
                "unprovable_range",
                "slow_consumer",
                "rate_limited",
            ],
            row["reason"],
        ),
    )
