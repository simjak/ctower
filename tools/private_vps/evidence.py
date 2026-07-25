"""Fail-closed verification of bound private-VPS evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tools.private_vps.manifest import PacketError, digest_file, load_model, resolve_artifact
from tools.private_vps.models import (
    ArtifactFile,
    Claim,
    Cp3dManifest,
    DeploymentBindings,
    EvidenceManifest,
    ScheduledOccurrence,
    SchedulerReceipt,
)
from tools.private_vps.preflight import verify_configuration

__all__ = ["EvidenceSummary", "verify_evidence"]

_REQUIRED_SINGLETONS = {
    "deployment_preflight",
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
_MINIMUM_WORKING_DAYS = 5
_SATURDAY_INDEX = 5


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    artifact_count: int
    qualifying_working_days: int


def verify_evidence(path: Path, claim: Claim) -> EvidenceSummary:
    """Verify exact bound bytes and claim-specific independent evidence."""
    manifest = load_model(path, EvidenceManifest, field="evidence")
    if manifest.claim != claim:
        raise PacketError("claim_changed", "claim")
    deployment_path = _verified_file(
        path.parent,
        manifest.deployment_manifest,
        "deployment_manifest",
    )
    deployment = load_model(deployment_path, DeploymentBindings, field="deployment_manifest")
    _verify_bound_inputs(manifest, deployment, deployment_path.parent)
    artifacts = _verify_artifacts(path.parent, manifest.artifacts)
    working_days = _verify_occurrences(path.parent, manifest, artifacts)
    if claim == "i1_exit":
        _verify_i1_exit(path.parent, manifest)
    return EvidenceSummary(
        artifact_count=len(manifest.artifacts),
        qualifying_working_days=len(working_days),
    )


def _verify_bound_inputs(
    manifest: EvidenceManifest,
    deployment: DeploymentBindings,
    deployment_base: Path,
) -> None:
    inputs = manifest.bound_inputs
    if inputs.source != deployment.source:
        raise PacketError("source_changed", "bound_inputs.source")
    if inputs.control_image != deployment.images.control:
        raise PacketError("control_image_changed", "bound_inputs.control_image")
    if inputs.configuration != deployment.configuration:
        raise PacketError("configuration_changed", "bound_inputs.configuration")
    verify_configuration(deployment, deployment_base)


def _verify_artifacts(base: Path, artifacts: tuple[ArtifactFile, ...]) -> dict[str, ArtifactFile]:
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    if len(by_id) != len(artifacts):
        raise PacketError("duplicate_artifact", "artifacts.artifact_id")
    if len({artifact.path for artifact in artifacts}) != len(artifacts):
        raise PacketError("duplicate_artifact", "artifacts.path")
    singleton_counts = {
        kind: sum(artifact.kind == kind for artifact in artifacts) for kind in _REQUIRED_SINGLETONS
    }
    if any(count == 0 for count in singleton_counts.values()):
        raise PacketError("missing_artifact", "artifacts")
    if any(count > 1 for count in singleton_counts.values()):
        raise PacketError("duplicate_artifact", "artifacts.kind")
    for artifact in artifacts:
        _verified_file(base, artifact, f"artifacts.{artifact.artifact_id}")
    return by_id


def _verify_occurrences(
    base: Path,
    manifest: EvidenceManifest,
    artifacts: dict[str, ArtifactFile],
) -> set[date]:
    if len({item.occurrence_id for item in manifest.occurrences}) != len(manifest.occurrences):
        raise PacketError("duplicate_occurrence", "occurrences")
    working_days: set[date] = set()
    for occurrence in manifest.occurrences:
        _verify_occurrence(base, occurrence, artifacts)
        if occurrence.working_day.weekday() >= _SATURDAY_INDEX:
            raise PacketError("non_working_day", "occurrences.working_day")
        working_days.add(occurrence.working_day)
    if len(working_days) < _MINIMUM_WORKING_DAYS:
        raise PacketError("insufficient_working_days", "occurrences")
    return working_days


def _verify_occurrence(
    base: Path,
    occurrence: ScheduledOccurrence,
    artifacts: dict[str, ArtifactFile],
) -> None:
    if occurrence.trigger != "scheduled" or occurrence.origin != "routine_scheduler":
        raise PacketError("manual_occurrence", "occurrences.trigger")
    if occurrence.manual_command_ref is not None:
        raise PacketError("manual_occurrence", "occurrences.manual_command_ref")
    result = artifacts.get(occurrence.result_artifact_id)
    receipt = artifacts.get(occurrence.scheduler_receipt_artifact_id or "")
    if result is None or result.kind != "synthetic_occurrence":
        raise PacketError("missing_artifact", "occurrences.result_artifact_id")
    if receipt is None or receipt.kind != "scheduler_receipt":
        raise PacketError("missing_scheduler_receipt", "occurrences.scheduler_receipt_artifact_id")
    receipt_path = resolve_artifact(base, receipt.path, field="occurrences.scheduler_receipt")
    parsed = load_model(receipt_path, SchedulerReceipt, field="scheduler_receipt")
    expected = (
        occurrence.occurrence_id,
        occurrence.schedule_ref,
        occurrence.scheduled_for,
    )
    if (parsed.occurrence_id, parsed.schedule_ref, parsed.scheduled_for) != expected:
        raise PacketError("scheduler_receipt_changed", "occurrences.scheduler_receipt")


def _verify_i1_exit(
    base: Path,
    manifest: EvidenceManifest,
) -> None:
    local_adapter = (
        manifest.object_adapter == "local_encrypted_filesystem"
        or manifest.key_adapter == "local_file"
    )
    if local_adapter:
        raise PacketError("local_adapter_forbidden", "claim")
    if manifest.assurance != "cp3d" or manifest.durability_policy != "cutover_rpo0":
        raise PacketError("cp3d_required", "claim")
    if manifest.cp3d_manifest is None:
        raise PacketError("cp3d_manifest_missing", "cp3d_manifest")
    cp3d_path = _verified_file(base, manifest.cp3d_manifest, "cp3d_manifest")
    cp3d = load_model(cp3d_path, Cp3dManifest, field="cp3d_manifest")
    _verify_cp3d(cp3d_path, cp3d, manifest)


def _verify_cp3d(
    path: Path,
    cp3d: Cp3dManifest,
    manifest: EvidenceManifest,
) -> None:
    if cp3d.source != manifest.bound_inputs.source:
        raise PacketError("cp3d_binding_changed", "cp3d_manifest.source")
    if cp3d.control_image != manifest.bound_inputs.control_image:
        raise PacketError("cp3d_binding_changed", "cp3d_manifest.control_image")
    if cp3d.configuration != manifest.bound_inputs.configuration:
        raise PacketError("cp3d_binding_changed", "cp3d_manifest.configuration")
    if cp3d.deployment_manifest_sha256 != manifest.deployment_manifest.sha256:
        raise PacketError("cp3d_binding_changed", "cp3d_manifest.deployment_manifest_sha256")
    _verified_file(path.parent, cp3d.verification_artifact, "cp3d_manifest.verification_artifact")


def _verified_file(base: Path, artifact: ArtifactFile, field: str) -> Path:
    path = resolve_artifact(base, artifact.path, field=field)
    if digest_file(path, field=field) != artifact.sha256:
        raise PacketError("artifact_changed", field)
    return path
