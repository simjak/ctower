"""Postgres Adapter for Record-owned recovery evidence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.record._integrity import inventory_failures
from ctower_kernel.record._recovery_sql import (
    begin_restore,
    complete_restore,
    enable_restore,
    insert_anchor,
    insert_backup,
    insert_installation,
    insert_inventory,
    reads_enabled,
)
from ctower_kernel.record.recovery import (
    AcceptedRoot,
    AnchorRecord,
    BackupRecord,
    InstallationIdentity,
    InventoryRevision,
    RecoveryPolicy,
    RestoreReport,
)

__all__ = ["PostgresRecovery"]


class PostgresRecovery:
    """Persist only externally verified, policy-valid recovery facts."""

    def __init__(self, dsn: str, *, policy: RecoveryPolicy | None = None) -> None:
        self._dsn = dsn
        self._policy = policy or RecoveryPolicy()

    def record_backup(self, backup: BackupRecord) -> None:
        """Append one complete verified backup and receipt."""

        insert_backup(self._dsn, backup)

    def record_anchor(
        self,
        anchor: AnchorRecord,
        roots: tuple[AcceptedRoot, ...],
        *,
        signature_verified: bool,
    ) -> None:
        """Append an anchor only after digest and external signature verification."""

        expected = self._policy.build_anchor(
            roots,
            previous_anchor_sha256=anchor.previous_anchor_sha256,
        )
        if (
            not signature_verified
            or expected != anchor.anchor_sha256
            or roots[0].acceptance_position != anchor.source_start_position
            or roots[-1].acceptance_position != anchor.source_end_position
        ):
            raise ValueError("anchor receipt failed digest or signature verification")
        insert_anchor(self._dsn, anchor)

    def record_installation(
        self,
        identity: InstallationIdentity,
        *,
        signature_verified: bool,
    ) -> None:
        """Append only a root-signature-verified installation identity."""

        if not signature_verified:
            raise ValueError("installation identity signature verification failed")
        insert_installation(self._dsn, identity)

    def record_inventory(
        self,
        inventory: InventoryRevision,
        *,
        signature_verified: bool,
    ) -> None:
        """Append one exhaustive digest- and signature-verified revision."""

        active = frozenset(
            source.source_key for source in inventory.sources if source.activation == "active"
        )
        failures = inventory_failures(
            tuple(source.model_dump(mode="python") for source in inventory.sources),
            reconciled_source_keys=active,
        )
        if not signature_verified or failures:
            raise ValueError("inventory revision failed signature or source validation")
        insert_inventory(self._dsn, inventory)

    def begin_restore(
        self,
        *,
        restore_run_id: UUID,
        tenant_id: UUID,
        installation_id: UUID,
        backup_id: UUID,
        inventory_revision_id: UUID,
        accepted_source_position: int,
        restored_acceptance_position: int,
        artifact_rpo_seconds: int,
        started_at: datetime,
    ) -> None:
        """Open one isolated run in quarantine."""

        begin_restore(
            self._dsn,
            restore_run_id=restore_run_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            backup_id=backup_id,
            inventory_revision_id=inventory_revision_id,
            accepted_source_position=accepted_source_position,
            restored_acceptance_position=restored_acceptance_position,
            artifact_rpo_seconds=artifact_rpo_seconds,
            started_at=started_at,
        )

    def complete_restore(self, report: RestoreReport) -> str:
        """Persist ordered steps/findings and retain quarantine."""

        return complete_restore(self._dsn, report)

    def enable(
        self,
        *,
        enablement_id: UUID,
        restore_run_id: UUID,
        tenant_id: UUID,
        installation_id: UUID,
        report_sha256: str,
        authority_ref: str,
        enabled_at: datetime,
    ) -> None:
        """Append one exact enablement after rechecking every persisted proof."""

        enable_restore(
            self._dsn,
            enablement_id=enablement_id,
            restore_run_id=restore_run_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            report_sha256=report_sha256,
            authority_ref=authority_ref,
            enabled_at=enabled_at,
        )

    def reads_enabled(
        self,
        *,
        tenant_id: UUID,
        installation_id: UUID,
        report_sha256: str,
    ) -> bool:
        """Require one exact installation/report enablement receipt."""

        return reads_enabled(
            self._dsn,
            tenant_id=tenant_id,
            installation_id=installation_id,
            report_sha256=report_sha256,
        )
