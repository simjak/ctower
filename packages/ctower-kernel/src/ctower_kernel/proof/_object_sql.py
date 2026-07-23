"""Proof-owned dual-read object expansion and durable erasure SQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from ctower_kernel.proof.objects import ObjectIntegrityError, StoredObject

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObjectRow:
    state: str
    content: bytes | None
    receipt: StoredObject | None


def insert_external_object(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    producer_id: UUID,
    content: bytes,
    receipt: StoredObject,
    *,
    recorded_at: datetime,
) -> None:
    digest = _digest(receipt.artifact_digest)
    connection.execute(
        """
        INSERT INTO proof_objects (
            tenant_id, artifact_digest, content, producer_id, recorded_at, storage_state,
            object_key, object_version, ciphertext_sha256, key_reference, key_version,
            wrapped_key_sha256, external_verified_at
        ) VALUES (
            %s, %s, %s, %s, %s, 'external_verified', %s, %s, %s, %s, %s, %s, %s
        ) ON CONFLICT (tenant_id, artifact_digest) DO UPDATE
        SET storage_state = EXCLUDED.storage_state,
            object_key = EXCLUDED.object_key,
            object_version = EXCLUDED.object_version,
            ciphertext_sha256 = EXCLUDED.ciphertext_sha256,
            key_reference = EXCLUDED.key_reference,
            key_version = EXCLUDED.key_version,
            wrapped_key_sha256 = EXCLUDED.wrapped_key_sha256,
            external_verified_at = EXCLUDED.external_verified_at
        WHERE proof_objects.storage_state = 'inline_compatible'
          AND proof_objects.content = EXCLUDED.content
        """,
        (
            tenant_id,
            digest,
            content,
            producer_id,
            recorded_at,
            receipt.object_key,
            receipt.object_version,
            _digest(receipt.ciphertext_sha256),
            receipt.key_reference,
            receipt.key_version,
            _digest(receipt.wrapped_key_sha256),
            receipt.verified_at,
        ),
    )
    row = connection.execute(
        """
        SELECT storage_state, object_key, object_version, ciphertext_sha256,
            key_reference, key_version, wrapped_key_sha256
        FROM proof_objects WHERE tenant_id = %s AND artifact_digest = %s
        """,
        (tenant_id, digest),
    ).fetchone()
    if row is None or not _row_matches(row, receipt):
        raise ObjectIntegrityError("existing object metadata conflicts with verified upload")
    receipt_id = uuid5(
        NAMESPACE_URL,
        f"ctower:object:{tenant_id}:{receipt.artifact_digest}:{receipt.object_version}",
    )
    connection.execute(
        """
        INSERT INTO object_upload_receipts (
            receipt_id, tenant_id, artifact_digest, object_key, object_version,
            ciphertext_sha256, key_reference, key_version, wrapped_key_sha256,
            uploaded_at, verified_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, artifact_digest, object_key, object_version) DO NOTHING
        """,
        (
            receipt_id,
            tenant_id,
            digest,
            receipt.object_key,
            receipt.object_version,
            _digest(receipt.ciphertext_sha256),
            receipt.key_reference,
            receipt.key_version,
            _digest(receipt.wrapped_key_sha256),
            receipt.uploaded_at,
            receipt.verified_at,
        ),
    )


def load_object(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    artifact_digest: str,
) -> ObjectRow | None:
    row = connection.execute(
        """
        SELECT storage_state, content, object_key, object_version, ciphertext_sha256,
            key_reference, key_version, wrapped_key_sha256, recorded_at,
            external_verified_at
        FROM proof_objects WHERE tenant_id = %s AND artifact_digest = %s
        """,
        (tenant_id, _digest(artifact_digest)),
    ).fetchone()
    if row is None:
        return None
    state = str(row["storage_state"])
    content = bytes(cast(bytes, row["content"])) if row["content"] is not None else None
    receipt = _receipt_from_row(artifact_digest, row) if state == "external_verified" else None
    return ObjectRow(state, content, receipt)


def mark_erased(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    artifact_digest: str,
    receipt: StoredObject,
    *,
    tombstone_id: UUID,
    authority_ref: str,
    reason: str,
    erased_at: datetime,
) -> None:
    updated = connection.execute(
        """
        UPDATE proof_objects
        SET content = NULL, storage_state = 'erased', object_key = NULL, object_version = NULL
        WHERE tenant_id = %s AND artifact_digest = %s
          AND storage_state = 'external_verified'
          AND object_key = %s AND object_version = %s
        """,
        (
            tenant_id,
            _digest(artifact_digest),
            receipt.object_key,
            receipt.object_version,
        ),
    )
    if updated.rowcount != 1:
        raise ObjectIntegrityError("object erasure metadata changed before tombstone commit")
    connection.execute(
        """
        INSERT INTO object_erasure_tombstones (
            tombstone_id, tenant_id, artifact_digest, erased_object_key,
            erased_object_version, erased_key_reference, authority_ref, reason, erased_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            tombstone_id,
            tenant_id,
            _digest(artifact_digest),
            receipt.object_key,
            receipt.object_version,
            receipt.key_reference,
            authority_ref,
            reason,
            erased_at,
        ),
    )


def inline_objects(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> tuple[tuple[str, bytes, UUID, datetime], ...]:
    rows = connection.execute(
        """
        SELECT artifact_digest, content, producer_id, recorded_at
        FROM proof_objects
        WHERE tenant_id = %s AND storage_state = 'inline_compatible'
        ORDER BY artifact_digest
        """,
        (tenant_id,),
    ).fetchall()
    return tuple(
        (
            f"sha256:{bytes(cast(bytes, row['artifact_digest'])).hex()}",
            bytes(cast(bytes, row["content"])),
            cast(UUID, row["producer_id"]),
            cast(datetime, row["recorded_at"]),
        )
        for row in rows
    )


def record_backfill(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    producer_id: UUID,
    content: bytes,
    receipt: StoredObject,
    *,
    recorded_at: datetime,
    clear_inline: bool,
) -> None:
    insert_external_object(
        connection,
        tenant_id,
        producer_id,
        content,
        receipt,
        recorded_at=recorded_at,
    )
    if clear_inline:
        connection.execute(
            """
            UPDATE proof_objects SET content = NULL
            WHERE tenant_id = %s AND artifact_digest = %s
              AND storage_state = 'external_verified'
            """,
            (tenant_id, _digest(receipt.artifact_digest)),
        )
    receipt_id = uuid5(
        NAMESPACE_URL,
        f"ctower:backfill:{tenant_id}:{receipt.artifact_digest}:{receipt.object_version}",
    )
    connection.execute(
        """
        INSERT INTO object_backfill_receipts (
            receipt_id, tenant_id, artifact_digest, before_sha256, after_sha256,
            object_version, inline_cleared, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, artifact_digest, object_version) DO NOTHING
        """,
        (
            receipt_id,
            tenant_id,
            _digest(receipt.artifact_digest),
            _digest(receipt.artifact_digest),
            _digest(receipt.artifact_digest),
            receipt.object_version,
            clear_inline,
            receipt.verified_at,
        ),
    )


def _receipt_from_row(artifact_digest: str, row: dict[str, object]) -> StoredObject:
    required = (
        "object_key",
        "object_version",
        "ciphertext_sha256",
        "key_reference",
        "key_version",
        "wrapped_key_sha256",
        "external_verified_at",
    )
    if any(row[field] is None for field in required):
        raise ObjectIntegrityError("external object metadata is incomplete")
    return StoredObject(
        artifact_digest=artifact_digest,
        object_key=str(row["object_key"]),
        object_version=str(row["object_version"]),
        ciphertext_sha256=f"sha256:{bytes(cast(bytes, row['ciphertext_sha256'])).hex()}",
        key_reference=str(row["key_reference"]),
        key_version=str(row["key_version"]),
        wrapped_key_sha256=f"sha256:{bytes(cast(bytes, row['wrapped_key_sha256'])).hex()}",
        uploaded_at=cast(datetime, row["recorded_at"]),
        verified_at=cast(datetime, row["external_verified_at"]),
    )


def _row_matches(row: dict[str, object], receipt: StoredObject) -> bool:
    return (
        row["storage_state"] == "external_verified"
        and row["object_key"] == receipt.object_key
        and row["object_version"] == receipt.object_version
        and bytes(cast(bytes, row["ciphertext_sha256"])) == _digest(receipt.ciphertext_sha256)
        and row["key_reference"] == receipt.key_reference
        and row["key_version"] == receipt.key_version
        and bytes(cast(bytes, row["wrapped_key_sha256"])) == _digest(receipt.wrapped_key_sha256)
    )


def _digest(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))
