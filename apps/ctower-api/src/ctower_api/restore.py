"""Isolated-restore quarantine composition; not a product API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ctower_kernel.record.postgres_recovery import PostgresRecovery
from ctower_kernel.record.recovery import (
    InventoryRevision,
    RecoveryPolicy,
    RestoreCheck,
    RestoreReport,
    RestoreStepKind,
    SignatureVerification,
)

__all__ = ["RestoreEvidence", "RestoreGate", "RestoreVerifier"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CheckEvidence(_StrictModel):
    """Digest-bound outcome from one fixed restore operation."""

    outcome: Literal["pass", "fail"]
    evidence_sha256: str
    detail: str


class RestoreEvidence(_StrictModel):
    """All fixed checks required by the isolated restore order."""

    database_recovered: CheckEvidence
    object_access_recovered: CheckEvidence
    key_access_recovered: CheckEvidence
    erasure_reapplied: CheckEvidence
    migrations_verified: CheckEvidence
    chains_verified: CheckEvidence
    anchors_verified: CheckEvidence
    objects_verified: CheckEvidence
    tombstones_verified: CheckEvidence
    inventory_verified: CheckEvidence
    journals_reconciled: CheckEvidence
    synthetic_verified: CheckEvidence

    def ordered(self) -> tuple[RestoreCheck, ...]:
        """Materialize the only legal check sequence."""

        return tuple(
            RestoreCheck(
                kind=kind,
                outcome=evidence.outcome,
                evidence_sha256=evidence.evidence_sha256,
                detail=evidence.detail,
            )
            for kind, evidence in (
                (RestoreStepKind.DATABASE_RECOVERED, self.database_recovered),
                (RestoreStepKind.OBJECT_ACCESS_RECOVERED, self.object_access_recovered),
                (RestoreStepKind.KEY_ACCESS_RECOVERED, self.key_access_recovered),
                (RestoreStepKind.ERASURE_REAPPLIED, self.erasure_reapplied),
                (RestoreStepKind.MIGRATIONS_VERIFIED, self.migrations_verified),
                (RestoreStepKind.CHAINS_VERIFIED, self.chains_verified),
                (RestoreStepKind.ANCHORS_VERIFIED, self.anchors_verified),
                (RestoreStepKind.OBJECTS_VERIFIED, self.objects_verified),
                (RestoreStepKind.TOMBSTONES_VERIFIED, self.tombstones_verified),
                (RestoreStepKind.INVENTORY_VERIFIED, self.inventory_verified),
                (RestoreStepKind.JOURNALS_RECONCILED, self.journals_reconciled),
                (RestoreStepKind.SYNTHETIC_VERIFIED, self.synthetic_verified),
            )
        )


class RestoreVerifier:
    """Record a quarantined run and evaluate only recovered evidence."""

    def __init__(
        self,
        recovery: PostgresRecovery,
        *,
        policy: RecoveryPolicy | None = None,
    ) -> None:
        self._recovery = recovery
        self._policy = policy or RecoveryPolicy()

    def verify(
        self,
        *,
        restore_run_id: UUID,
        tenant_id: UUID,
        installation_id: UUID,
        backup_id: UUID,
        inventory: InventoryRevision,
        inventory_verification: SignatureVerification,
        reconciled_source_keys: frozenset[str],
        accepted_source_position: int,
        restored_acceptance_position: int,
        artifact_rpo_seconds: int,
        started_at: datetime,
        completed_at: datetime,
        evidence: RestoreEvidence,
    ) -> tuple[RestoreReport, str]:
        """Persist one complete report without enabling ordinary reads."""

        self._recovery.begin_restore(
            restore_run_id=restore_run_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            backup_id=backup_id,
            inventory_revision_id=inventory.inventory_revision_id,
            accepted_source_position=accepted_source_position,
            restored_acceptance_position=restored_acceptance_position,
            artifact_rpo_seconds=artifact_rpo_seconds,
            started_at=started_at,
        )
        report = self._policy.evaluate_restore(
            restore_run_id=restore_run_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            backup_id=backup_id,
            inventory=inventory,
            inventory_verification=inventory_verification,
            reconciled_source_keys=reconciled_source_keys,
            accepted_source_position=accepted_source_position,
            restored_acceptance_position=restored_acceptance_position,
            artifact_rpo_seconds=artifact_rpo_seconds,
            started_at=started_at,
            completed_at=completed_at,
            checks=evidence.ordered(),
        )
        return report, self._recovery.complete_restore(report)


class RestoreGate:
    """Deny ordinary reads until exact installation/report enablement."""

    def __init__(
        self,
        recovery: PostgresRecovery,
        *,
        tenant_id: UUID,
        installation_id: UUID,
        report_sha256: str,
    ) -> None:
        self._recovery = recovery
        self._tenant_id = tenant_id
        self._installation_id = installation_id
        self._report_sha256 = report_sha256

    def require_ordinary_reads(self) -> None:
        """Fail closed across restarts until one exact receipt exists."""

        if not self._recovery.reads_enabled(
            tenant_id=self._tenant_id,
            installation_id=self._installation_id,
            report_sha256=self._report_sha256,
        ):
            raise PermissionError("restore quarantine denies ordinary reads")

    def effects_enabled(self) -> Literal[False]:
        """I1 effects remain disabled even after read enablement."""

        return False
