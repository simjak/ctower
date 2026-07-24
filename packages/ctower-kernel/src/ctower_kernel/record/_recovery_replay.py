"""Exact immutable replay checks shared by recovery SQL operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record.recovery import (
    AnchorRecord,
    InventoryRevision,
    RecoveryReplayConflictError,
)

__all__: tuple[str, ...] = ()


def require_exact_row(
    connection: psycopg.Connection[dict[str, object]],
    query: str,
    parameters: Sequence[object],
    *,
    label: str,
) -> None:
    """Require one stored row to equal the complete proposed semantic receipt."""

    if connection.execute(query, parameters).fetchone() is None:
        raise RecoveryReplayConflictError(f"{label} replay changed immutable semantics")


def lock_recovery_chain(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    chain: str,
) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"ctower:recovery:{chain}:{tenant_id}",),
    )


def require_anchor_replay(
    connection: psycopg.Connection[dict[str, object]],
    anchor: AnchorRecord,
) -> None:
    require_exact_row(
        connection,
        """
        SELECT 1 FROM record_anchor_receipts
        WHERE anchor_id = %s AND tenant_id = %s
          AND source_start_position = %s AND source_end_position = %s
          AND previous_anchor_sha256 IS NOT DISTINCT FROM %s
          AND anchor_sha256 = %s AND signature = %s
          AND signing_key_reference = %s AND signing_key_version = %s
          AND public_key_sha256 = %s AND object_key = %s AND object_version = %s
          AND anchored_at = %s
        """,
        (
            anchor.anchor_id,
            anchor.tenant_id,
            anchor.source_start_position,
            anchor.source_end_position,
            _optional_digest(anchor.previous_anchor_sha256),
            _digest(anchor.anchor_sha256),
            anchor.signature,
            anchor.signing_key_reference,
            anchor.signing_key_version,
            _digest(anchor.public_key_sha256),
            anchor.object_key,
            anchor.object_version,
            anchor.anchored_at,
        ),
        label="anchor",
    )


def require_anchor_predecessor(
    anchor: AnchorRecord,
    previous: dict[str, object] | None,
) -> None:
    if previous is None:
        if anchor.source_start_position != 1 or anchor.previous_anchor_sha256 is not None:
            raise ValueError("anchor genesis must start at position one without a predecessor")
        return
    expected_start = cast(int, previous["source_end_position"]) + 1
    expected_digest = f"sha256:{_stored_digest(previous['anchor_sha256']).hex()}"
    if (
        anchor.source_start_position != expected_start
        or anchor.previous_anchor_sha256 != expected_digest
    ):
        raise ValueError("anchor range or predecessor is not continuous")


def require_inventory_replay(
    connection: psycopg.Connection[dict[str, object]],
    inventory: InventoryRevision,
) -> None:
    require_exact_row(
        connection,
        """
        SELECT 1 FROM expected_source_inventory_revisions
        WHERE inventory_revision_id = %s AND tenant_id = %s AND schema_id = %s
          AND revision_number = %s AND revision_sha256 = %s
          AND previous_revision_sha256 IS NOT DISTINCT FROM %s
          AND signature = %s AND signing_key_reference = %s
          AND signing_key_version = %s AND public_key_sha256 = %s
          AND object_key = %s AND object_version = %s AND created_at = %s
        """,
        (
            inventory.inventory_revision_id,
            inventory.tenant_id,
            inventory.schema_id,
            inventory.revision_number,
            _digest(inventory.revision_sha256),
            _optional_digest(inventory.previous_revision_sha256),
            inventory.signature,
            inventory.signing_key_reference,
            inventory.signing_key_version,
            _digest(inventory.public_key_sha256),
            inventory.object_key,
            inventory.object_version,
            inventory.created_at,
        ),
        label="inventory",
    )
    count = connection.execute(
        """
        SELECT count(*) AS value FROM expected_source_inventory_entries
        WHERE inventory_revision_id = %s
        """,
        (inventory.inventory_revision_id,),
    ).fetchone()
    if count is None or cast(int, count["value"]) != len(inventory.sources):
        raise RecoveryReplayConflictError("inventory replay changed immutable source entries")
    for source in inventory.sources:
        require_exact_row(
            connection,
            """
            SELECT 1 FROM expected_source_inventory_entries
            WHERE inventory_revision_id = %s AND tenant_id = %s AND source_key = %s
              AND source_kind = %s AND activation = %s AND cursor_declaration = %s
              AND source_count = %s AND trust_root_ref IS NOT DISTINCT FROM %s
              AND trusted_cursor IS NOT DISTINCT FROM %s
              AND activation_event_ref IS NOT DISTINCT FROM %s
            """,
            (
                inventory.inventory_revision_id,
                inventory.tenant_id,
                source.source_key,
                source.source_kind,
                source.activation,
                source.cursor_declaration,
                source.source_count,
                source.trust_root_ref,
                source.trusted_cursor,
                source.activation_event_ref,
            ),
            label=f"inventory source {source.source_key}",
        )


def require_inventory_predecessor(
    inventory: InventoryRevision,
    previous: dict[str, object] | None,
) -> None:
    if previous is None:
        if inventory.revision_number != 1 or inventory.previous_revision_sha256 is not None:
            raise ValueError("inventory genesis must be revision one without a predecessor")
        return
    expected_number = cast(int, previous["revision_number"]) + 1
    expected_digest = f"sha256:{_stored_digest(previous['revision_sha256']).hex()}"
    if (
        inventory.revision_number != expected_number
        or inventory.previous_revision_sha256 != expected_digest
    ):
        raise ValueError("inventory revision or predecessor is not continuous")


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _optional_digest(value: str | None) -> bytes | None:
    return _digest(value) if value is not None else None


def _stored_digest(value: object) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("database digest has an unexpected representation")
    return bytes(value)
