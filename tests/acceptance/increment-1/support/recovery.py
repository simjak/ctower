"""Factories for real-Postgres recovery acceptance scenarios."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

import psycopg

from ctower_kernel.record.recovery import (
    AcceptedRoot,
    AnchorRecord,
    BackupManifest,
    BackupVerificationReceipt,
    ExpectedSource,
    InstallationIdentity,
    InventoryRevision,
    SignatureVerification,
)

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
__all__ = [
    "NOW",
    "accepted_roots",
    "backup",
    "installation",
    "inventory",
    "inventory_with_sources",
    "signature_verification",
]


def backup(backup_id: UUID, tenant_id: UUID) -> BackupVerificationReceipt:
    return BackupVerificationReceipt(
        manifest=BackupManifest(
            backup_id=backup_id,
            tenant_id=tenant_id,
            repository_ref="backup-ref:test/repository",
            repository_object_version="version-1",
            base_backup_sha256="sha256:" + "2" * 64,
            wal_start_lsn="0/10",
            wal_stop_lsn="0/20",
            logical_dump_sha256="sha256:" + "3" * 64,
            object_manifest_sha256="sha256:" + "4" * 64,
            migration_manifest_sha256="sha256:" + "5" * 64,
            key_reference="kms-ref:backup/key",
            key_version="v1",
            pgbackrest_sha256="sha256:" + "9" * 64,
            pg_dump_sha256="sha256:" + "a" * 64,
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=1),
        )
    )


def installation(tenant_id: UUID) -> InstallationIdentity:
    return InstallationIdentity(
        installation_id=uuid4(),
        tenant_id=tenant_id,
        identity_ref="installation-ref:test/isolated",
        signature="root-signed-installation",
        signing_key_reference="kms-ref:installation/signing",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "7" * 64,
        issued_at=NOW,
    )


def inventory(
    tenant_id: UUID,
    *,
    revision_number: int = 1,
    previous_revision_sha256: str | None = None,
) -> InventoryRevision:
    sources = (
        _source("ctower.root-supervisor.default", "root_supervisor_journal"),
        _source("ctower.effect.default", "effect_journal"),
        _source("ctower.provider.default", "provider_journal"),
    )
    revision_id = uuid4()
    payload: dict[str, object] = {
        "schema_id": "ctower.expected-source-inventory/v1",
        "inventory_revision_id": str(revision_id),
        "tenant_id": str(tenant_id),
        "revision_number": revision_number,
        "previous_revision_sha256": previous_revision_sha256,
        "signing_key_reference": "kms-ref:restore/inventory",
        "signing_key_version": "v1",
        "public_key_sha256": "sha256:" + "8" * 64,
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    return InventoryRevision(
        schema_id="ctower.expected-source-inventory/v1",
        inventory_revision_id=revision_id,
        tenant_id=tenant_id,
        revision_number=revision_number,
        previous_revision_sha256=previous_revision_sha256,
        revision_sha256=digest,
        signature="external-kms-signature",
        signing_key_reference="kms-ref:restore/inventory",
        signing_key_version="v1",
        public_key_sha256="sha256:" + "8" * 64,
        object_key=f"operations/inventory/revision-{revision_number}.json",
        object_version=f"version-{revision_number}",
        created_at=NOW,
        sources=sources,
    )


def signature_verification(
    signed: AnchorRecord | InstallationIdentity | InventoryRevision,
    *,
    verified: bool = True,
) -> SignatureVerification:
    if isinstance(signed, AnchorRecord):
        digest = signed.anchor_sha256
        signed_at = signed.anchored_at
    elif isinstance(signed, InstallationIdentity):
        digest = signed.identity_sha256
        signed_at = signed.issued_at
    else:
        digest = signed.revision_sha256
        signed_at = signed.created_at
    return SignatureVerification(
        digest=digest,
        signature=signed.signature,
        signing_key_reference=signed.signing_key_reference,
        signing_key_version=signed.signing_key_version,
        public_key_sha256=signed.public_key_sha256,
        signed_at=signed_at,
        verified=verified,
        verified_at=signed_at + timedelta(seconds=1),
        reason="valid" if verified else "invalid_signature",
    )


def inventory_with_sources(
    inventory: InventoryRevision,
    sources: tuple[ExpectedSource, ...],
) -> InventoryRevision:
    """Recompute the signed body after changing one source entry."""

    changed = inventory.model_copy(update={"sources": sources})
    payload = changed.model_dump(mode="json")
    for omitted in ("revision_sha256", "signature", "object_key", "object_version"):
        payload.pop(omitted)
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    return changed.model_copy(update={"revision_sha256": digest})


def accepted_roots(dsn: str, tenant_id: UUID) -> tuple[AcceptedRoot, ...]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            """
            SELECT acceptance_position, command_root
            FROM durability_acceptance_confirmations
            WHERE tenant_id = %s
            ORDER BY acceptance_position
            """,
            (tenant_id,),
        ).fetchall()
    return tuple(
        AcceptedRoot(
            acceptance_position=int(cast(int, row[0])),
            command_root=f"sha256:{bytes(cast(bytes, row[1])).hex()}",
        )
        for row in rows
    )


def _source(
    key: str,
    kind: Literal["root_supervisor_journal", "effect_journal", "provider_journal"],
) -> ExpectedSource:
    return ExpectedSource(
        source_key=key,
        source_kind=kind,
        activation="not_exercised",
        cursor_declaration="zero_source",
        source_count=0,
    )
