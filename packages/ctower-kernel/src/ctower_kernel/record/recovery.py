"""Record-owned disaster evidence and restore-enablement policy."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from ctower_kernel.record._integrity import (
    anchor_digest,
    inventory_digest,
    inventory_failures,
)

__all__ = [
    "AcceptedRoot",
    "AnchorRecord",
    "BackupRecord",
    "ExpectedSource",
    "InstallationIdentity",
    "InventoryRevision",
    "RecoveryPolicy",
    "RestoreCheck",
    "RestoreFinding",
    "RestoreReport",
    "RestoreStepKind",
]

type Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
type StableReference = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9._:/-]{2,255}$"),
]
_MAX_ARTIFACT_RPO_SECONDS = 300
_MAX_RESTORE_RTO_SECONDS = 14_400


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AcceptedRoot(_StrictModel):
    """One accepted command root consumed by an external anchor."""

    acceptance_position: int
    command_root: Digest


class AnchorRecord(_StrictModel):
    """Append-only signed anchor metadata after conditional object creation."""

    anchor_id: UUID
    tenant_id: UUID
    source_start_position: int
    source_end_position: int
    previous_anchor_sha256: Digest | None
    anchor_sha256: Digest
    signature: str
    signing_key_reference: StableReference
    signing_key_version: str
    public_key_sha256: Digest
    object_key: str
    object_version: str
    anchored_at: datetime


class BackupRecord(_StrictModel):
    """Verified complete database/object backup evidence."""

    backup_id: UUID
    verification_receipt_id: UUID
    tenant_id: UUID
    manifest_sha256: Digest
    repository_ref: StableReference
    repository_object_version: str
    base_backup_sha256: Digest
    wal_start_lsn: str
    wal_stop_lsn: str
    logical_dump_sha256: Digest
    object_manifest_sha256: Digest
    migration_manifest_sha256: Digest
    key_reference: StableReference
    key_version: str
    started_at: datetime
    completed_at: datetime
    base_verified: Literal[True]
    wal_verified: Literal[True]
    logical_dump_verified: Literal[True]
    objects_verified: Literal[True]
    key_reference_verified: Literal[True]


class InstallationIdentity(_StrictModel):
    """Root-signed installation identity that prevents restored DB reuse."""

    installation_id: UUID
    tenant_id: UUID
    identity_ref: StableReference
    identity_sha256: Digest
    signature: str
    signing_key_reference: StableReference
    signing_key_version: str
    public_key_sha256: Digest
    issued_at: datetime


class ExpectedSource(_StrictModel):
    """One exhaustive external journal declaration."""

    source_key: str
    source_kind: Literal[
        "root_supervisor_journal",
        "effect_journal",
        "provider_journal",
    ]
    activation: Literal["not_exercised", "active"]
    cursor_declaration: Literal["zero_source", "trusted_cursor"]
    source_count: int
    trust_root_ref: StableReference | None = None
    trusted_cursor: str | None = None
    activation_event_ref: StableReference | None = None


class InventoryRevision(_StrictModel):
    """Canonical signed expected-source inventory revision."""

    schema_id: Literal["ctower.expected-source-inventory/v1"]
    inventory_revision_id: UUID
    tenant_id: UUID
    revision_number: int
    previous_revision_sha256: Digest | None
    revision_sha256: Digest
    signature: str
    signing_key_reference: StableReference
    signing_key_version: str
    public_key_sha256: Digest
    object_key: str
    object_version: str
    created_at: datetime
    sources: tuple[ExpectedSource, ...]

    @model_validator(mode="after")
    def _canonical_digest(self) -> InventoryRevision:
        if inventory_digest(self.model_dump(mode="json")) != self.revision_sha256:
            raise ValueError("inventory revision digest mismatch")
        return self


class RestoreStepKind(StrEnum):
    """The only legal isolated-restore order."""

    DATABASE_RECOVERED = "database_recovered"
    OBJECT_ACCESS_RECOVERED = "object_access_recovered"
    KEY_ACCESS_RECOVERED = "key_access_recovered"
    ERASURE_REAPPLIED = "erasure_reapplied"
    MIGRATIONS_VERIFIED = "migrations_verified"
    CHAINS_VERIFIED = "chains_verified"
    ANCHORS_VERIFIED = "anchors_verified"
    OBJECTS_VERIFIED = "objects_verified"
    TOMBSTONES_VERIFIED = "tombstones_verified"
    INVENTORY_VERIFIED = "inventory_verified"
    JOURNALS_RECONCILED = "journals_reconciled"
    SYNTHETIC_VERIFIED = "synthetic_verified"


RESTORE_ORDER = tuple(RestoreStepKind)


class RestoreCheck(_StrictModel):
    """One ordered recovered-byte verification outcome."""

    kind: RestoreStepKind
    outcome: Literal["pass", "fail"]
    evidence_sha256: Digest
    detail: str


class RestoreFinding(_StrictModel):
    """One fail-closed finding retained in quarantine."""

    key: str
    severity: Literal["critical", "error"]
    reason: str
    evidence_sha256: Digest
    resolved: bool = False


class RestoreReport(_StrictModel):
    """Exact report bound to a future enablement receipt."""

    schema_id: Literal["ctower.restore-report/v1"] = "ctower.restore-report/v1"
    restore_run_id: UUID
    tenant_id: UUID
    installation_id: UUID
    backup_id: UUID
    inventory_revision_sha256: Digest
    accepted_source_position: int
    restored_acceptance_position: int
    accepted_rpo_seconds: int
    artifact_rpo_seconds: int
    rto_seconds: int
    started_at: datetime
    completed_at: datetime
    steps: tuple[RestoreCheck, ...]
    findings: tuple[RestoreFinding, ...]
    enablement_eligible: bool
    effects_enabled: Literal[False] = False


class RecoveryPolicy:
    """Compute anchors and restore decisions without provider or SQL handles."""

    def build_anchor(
        self,
        roots: tuple[AcceptedRoot, ...],
        *,
        previous_anchor_sha256: str | None,
    ) -> str:
        """Bind one contiguous accepted prefix to its predecessor."""

        return anchor_digest(
            previous_anchor_sha256,
            tuple((root.acceptance_position, root.command_root) for root in roots),
        )

    def evaluate_restore(
        self,
        *,
        restore_run_id: UUID,
        tenant_id: UUID,
        installation_id: UUID,
        backup_id: UUID,
        inventory: InventoryRevision,
        inventory_signature_verified: bool,
        reconciled_source_keys: frozenset[str],
        accepted_source_position: int,
        restored_acceptance_position: int,
        artifact_rpo_seconds: int,
        started_at: datetime,
        completed_at: datetime,
        checks: tuple[RestoreCheck, ...],
    ) -> RestoreReport:
        """Remain quarantined unless every ordered proof and target passes."""

        _validate_restore_order(checks)
        failures = list(
            inventory_failures(
                tuple(source.model_dump(mode="python") for source in inventory.sources),
                reconciled_source_keys=reconciled_source_keys,
            )
        )
        if not inventory_signature_verified:
            failures.append("inventory-signature-invalid")
        if restored_acceptance_position != accepted_source_position:
            failures.append("accepted-record-rpo-nonzero")
        if artifact_rpo_seconds > _MAX_ARTIFACT_RPO_SECONDS:
            failures.append("artifact-rpo-exceeded")
        if any(check.outcome == "fail" for check in checks):
            failures.append("restore-step-failed")
        rto_seconds = int((completed_at - started_at).total_seconds())
        if rto_seconds < 0 or rto_seconds > _MAX_RESTORE_RTO_SECONDS:
            failures.append("restore-rto-exceeded")
        findings = tuple(_finding(index, failure) for index, failure in enumerate(failures, 1))
        return RestoreReport(
            restore_run_id=restore_run_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            backup_id=backup_id,
            inventory_revision_sha256=inventory.revision_sha256,
            accepted_source_position=accepted_source_position,
            restored_acceptance_position=restored_acceptance_position,
            accepted_rpo_seconds=max(
                accepted_source_position - restored_acceptance_position,
                0,
            ),
            artifact_rpo_seconds=artifact_rpo_seconds,
            rto_seconds=max(rto_seconds, 0),
            started_at=started_at,
            completed_at=completed_at,
            steps=checks,
            findings=findings,
            enablement_eligible=not findings,
        )


def _validate_restore_order(checks: tuple[RestoreCheck, ...]) -> None:
    if tuple(check.kind for check in checks) != RESTORE_ORDER:
        raise ValueError("restore checks must be complete and strictly ordered")


def _finding(index: int, failure: str) -> RestoreFinding:
    return RestoreFinding(
        key=f"restore.{index:02d}.{failure}",
        severity="critical",
        reason=failure,
        evidence_sha256=f"sha256:{'0' * 64}",
    )
