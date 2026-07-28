"""Fail-closed verification of bounded development-only VPS evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, timedelta
from pathlib import Path, PurePosixPath

from tools.private_vps.manifest import (
    MAX_ARTIFACT_BYTES,
    MAX_DOCUMENT_BYTES,
    ConfinedRoot,
    FileSnapshot,
    PacketError,
    load_snapshot,
)
from tools.private_vps.models import (
    ArtifactFile,
    CheckArtifact,
    Claim,
    DeploymentBindings,
    EvidenceManifest,
    ScheduledOccurrence,
    SchedulerReceipt,
    SyntheticResult,
)
from tools.private_vps.preflight import verify_configuration_confined

__all__ = ["EvidenceSummary", "verify_evidence"]

_CHECK_KINDS = {
    "tls_access",
    "database_bootstrap",
    "health_telemetry",
    "upgrade_rollback",
    "worker_restart",
    "host_reboot",
    "restore_report",
    "clean_install",
    "legacy_baseline",
}
_REQUIRED_SINGLETONS = {"deployment_contract_validation", *_CHECK_KINDS}
_CONTENT_SCHEMA = {
    "deployment_contract_validation": "ctower.private-vps-deployment/v1",
    **dict.fromkeys(_CHECK_KINDS, "ctower.private-vps-check/v1"),
    "synthetic_occurrence": "ctower.private-vps-synthetic-result/v1",
    "scheduler_receipt": "ctower.private-vps-scheduler-receipt/v1",
}
_MINIMUM_WORKING_DAYS = 5
_MAXIMUM_WINDOW_DAYS = 31
_MAXIMUM_AGGREGATE_ARTIFACT_BYTES = 1024 * 1024
_SATURDAY_INDEX = 5


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    artifact_count: int
    qualifying_working_days: int


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    descriptor: ArtifactFile
    snapshot: FileSnapshot


def verify_evidence(path: Path, claim: Claim) -> EvidenceSummary:
    """Verify a complete development recurrence from exact retained bytes."""
    if claim == "i1_exit":
        raise PacketError("unsupported_claim", "claim")
    absolute = path.absolute()
    with ConfinedRoot(absolute.parent) as root:
        manifest_snapshot = root.read(
            absolute.name,
            field="evidence",
            max_bytes=MAX_DOCUMENT_BYTES,
        )
        manifest = load_snapshot(manifest_snapshot, EvidenceManifest, field="evidence")
        if manifest.claim != claim:
            raise PacketError("claim_changed", "claim")
        artifacts = _verify_artifact_inventory(root, manifest)
        deployment = _verify_deployment(root, manifest, artifacts)
        working_days = _verify_recurrence(manifest, artifacts)
        _verify_check_documents(manifest, artifacts)
        _verify_bound_inputs(manifest, deployment)
    return EvidenceSummary(
        artifact_count=len(manifest.artifacts),
        qualifying_working_days=len(working_days),
    )


def _verify_artifact_inventory(
    root: ConfinedRoot,
    manifest: EvidenceManifest,
) -> dict[str, VerifiedArtifact]:
    descriptors = manifest.artifacts
    if len({item.artifact_id for item in descriptors}) != len(descriptors):
        raise PacketError("duplicate_artifact", "artifacts.artifact_id")
    if len({item.path for item in descriptors}) != len(descriptors):
        raise PacketError("duplicate_artifact", "artifacts.path")
    _verify_kind_counts(manifest)
    verified: dict[str, VerifiedArtifact] = {}
    aggregate = 0
    for artifact in descriptors:
        field = f"artifacts.{artifact.artifact_id}"
        snapshot = root.read(artifact.path, field=field, max_bytes=MAX_ARTIFACT_BYTES)
        aggregate += snapshot.size
        if aggregate > _MAXIMUM_AGGREGATE_ARTIFACT_BYTES:
            raise PacketError("artifact_aggregate_too_large", "artifacts")
        if snapshot.sha256 != artifact.sha256:
            raise PacketError("artifact_changed", field)
        if artifact.content_schema != _CONTENT_SCHEMA[artifact.kind]:
            raise PacketError("artifact_schema_changed", field)
        verified[artifact.artifact_id] = VerifiedArtifact(artifact, snapshot)
    return verified


def _verify_kind_counts(manifest: EvidenceManifest) -> None:
    counts = {
        kind: sum(item.kind == kind for item in manifest.artifacts) for kind in _REQUIRED_SINGLETONS
    }
    if any(count == 0 for count in counts.values()):
        raise PacketError("missing_artifact", "artifacts")
    if any(count > 1 for count in counts.values()):
        raise PacketError("duplicate_artifact", "artifacts.kind")
    occurrences = len(manifest.occurrences)
    if len(manifest.artifacts) != len(_REQUIRED_SINGLETONS) + 2 * occurrences:
        raise PacketError("artifact_cardinality", "artifacts")
    for kind in ("synthetic_occurrence", "scheduler_receipt"):
        if sum(item.kind == kind for item in manifest.artifacts) != occurrences:
            raise PacketError("artifact_cardinality", f"artifacts.{kind}")


def _verify_deployment(
    root: ConfinedRoot,
    manifest: EvidenceManifest,
    artifacts: dict[str, VerifiedArtifact],
) -> DeploymentBindings:
    artifact = artifacts.get(manifest.deployment_manifest_artifact_id)
    if artifact is None or artifact.descriptor.kind != "deployment_contract_validation":
        raise PacketError("missing_artifact", "deployment_manifest_artifact_id")
    deployment = load_snapshot(
        artifact.snapshot,
        DeploymentBindings,
        field="deployment_manifest",
    )
    prefix = PurePosixPath(artifact.descriptor.path).parent.as_posix()
    verify_configuration_confined(deployment, root, prefix="" if prefix == "." else prefix)
    return deployment


def _verify_recurrence(
    manifest: EvidenceManifest,
    artifacts: dict[str, VerifiedArtifact],
) -> tuple[date, ...]:
    expected_days = _working_days(manifest.window_start, manifest.window_end)
    actual_days = tuple(item.working_day for item in manifest.occurrences)
    if actual_days != expected_days:
        raise PacketError("incomplete_working_day_inventory", "occurrences")
    if len({item.occurrence_id for item in manifest.occurrences}) != len(actual_days):
        raise PacketError("duplicate_occurrence", "occurrences.occurrence_id")
    result_ids = {item.result_artifact_id for item in manifest.occurrences}
    receipt_ids = {item.scheduler_receipt_artifact_id for item in manifest.occurrences}
    if len(result_ids) != len(actual_days) or len(receipt_ids) != len(actual_days):
        raise PacketError("duplicate_occurrence_artifact", "occurrences")
    _verify_occurrence_inventory(artifacts, result_ids, receipt_ids)
    for occurrence in manifest.occurrences:
        _verify_occurrence(manifest, occurrence, artifacts)
    return expected_days


def _working_days(start: date, end: date) -> tuple[date, ...]:
    span = (end - start).days
    if span < 0 or span > _MAXIMUM_WINDOW_DAYS:
        raise PacketError("invalid_evidence_window", "window")
    days = tuple(
        start + timedelta(days=offset)
        for offset in range(span + 1)
        if (start + timedelta(days=offset)).weekday() < _SATURDAY_INDEX
    )
    if len(days) < _MINIMUM_WORKING_DAYS or not days or days[0] != start or days[-1] != end:
        raise PacketError("invalid_evidence_window", "window")
    return days


def _verify_occurrence_inventory(
    artifacts: dict[str, VerifiedArtifact],
    result_ids: set[str],
    receipt_ids: set[str],
) -> None:
    artifact_results = {
        key for key, value in artifacts.items() if value.descriptor.kind == "synthetic_occurrence"
    }
    artifact_receipts = {
        key for key, value in artifacts.items() if value.descriptor.kind == "scheduler_receipt"
    }
    if result_ids != artifact_results or receipt_ids != artifact_receipts:
        raise PacketError("incomplete_occurrence_inventory", "occurrences")


def _verify_occurrence(
    manifest: EvidenceManifest,
    occurrence: ScheduledOccurrence,
    artifacts: dict[str, VerifiedArtifact],
) -> None:
    if occurrence.schedule_ref != manifest.schedule_ref:
        raise PacketError("schedule_changed", "occurrences.schedule_ref")
    if occurrence.scheduled_for.utcoffset() != timedelta(0):
        raise PacketError("non_utc_schedule", "occurrences.scheduled_for")
    if occurrence.scheduled_for.astimezone(UTC).date() != occurrence.working_day:
        raise PacketError("scheduled_day_changed", "occurrences.scheduled_for")
    result_artifact = artifacts[occurrence.result_artifact_id]
    receipt_artifact = artifacts[occurrence.scheduler_receipt_artifact_id]
    result = load_snapshot(
        result_artifact.snapshot,
        SyntheticResult,
        field=f"results.{occurrence.occurrence_id}",
    )
    receipt = load_snapshot(
        receipt_artifact.snapshot,
        SchedulerReceipt,
        field=f"receipts.{occurrence.occurrence_id}",
    )
    _verify_occurrence_document(manifest, occurrence, result)
    _verify_occurrence_document(manifest, occurrence, receipt)


def _verify_occurrence_document(
    manifest: EvidenceManifest,
    occurrence: ScheduledOccurrence,
    document: SyntheticResult | SchedulerReceipt,
) -> None:
    actual = (
        document.occurrence_id,
        document.schedule_ref,
        document.scheduled_for,
        document.working_day,
        document.source,
        document.control_image,
        document.provenance,
    )
    expected = (
        occurrence.occurrence_id,
        manifest.schedule_ref,
        occurrence.scheduled_for,
        occurrence.working_day,
        manifest.bound_inputs.source,
        manifest.bound_inputs.control_image,
        manifest.provenance,
    )
    if actual != expected:
        raise PacketError("occurrence_artifact_changed", "occurrences")


def _verify_check_documents(
    manifest: EvidenceManifest,
    artifacts: dict[str, VerifiedArtifact],
) -> None:
    for artifact in artifacts.values():
        if artifact.descriptor.kind not in _CHECK_KINDS:
            continue
        parsed = load_snapshot(
            artifact.snapshot,
            CheckArtifact,
            field=f"checks.{artifact.descriptor.artifact_id}",
        )
        if parsed.artifact_id != artifact.descriptor.artifact_id:
            raise PacketError("check_artifact_changed", "artifacts.artifact_id")
        if parsed.kind != artifact.descriptor.kind:
            raise PacketError("check_artifact_changed", "artifacts.kind")
        if parsed.source != manifest.bound_inputs.source:
            raise PacketError("source_changed", "artifacts.source")
        if parsed.control_image != manifest.bound_inputs.control_image:
            raise PacketError("control_image_changed", "artifacts.control_image")
        observed_day = parsed.observed_at.astimezone(UTC).date()
        if not manifest.window_start <= observed_day <= manifest.window_end:
            raise PacketError("check_outside_window", "artifacts.observed_at")


def _verify_bound_inputs(
    manifest: EvidenceManifest,
    deployment: DeploymentBindings,
) -> None:
    inputs = manifest.bound_inputs
    if inputs.source != deployment.source:
        raise PacketError("source_changed", "bound_inputs.source")
    if inputs.control_image != deployment.images.control:
        raise PacketError("control_image_changed", "bound_inputs.control_image")
    if inputs.configuration != deployment.configuration:
        raise PacketError("configuration_changed", "bound_inputs.configuration")
