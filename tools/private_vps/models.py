"""Strict, immutable boundary models for the private-VPS source packet."""

from __future__ import annotations

import ipaddress
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

__all__ = [
    "ArtifactFile",
    "Cp3dManifest",
    "DeploymentBindings",
    "EvidenceManifest",
    "OperationResult",
    "SchedulerReceipt",
]

Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
GitObject = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9._:-]{2,127}$"),
]
ImageDigest = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z0-9][A-Za-z0-9._/:/-]*@sha256:[0-9a-f]{64}$",
    ),
]
Reference = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(?:alert-owner|credential-file|file|identity|object-root|schedule|"
            r"telemetry)-ref://[A-Za-z0-9._~:/-]+$"
        ),
    ),
]
RelativePath = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"),
]
AbsolutePath = Annotated[str, StringConstraints(min_length=2, max_length=300)]
FileMode = Literal["0400", "0440"]
Claim = Literal["development_rehearsal", "i1_exit"]
ArtifactKind = Literal[
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
    "synthetic_occurrence",
    "scheduler_receipt",
]


class FrozenModel(BaseModel):
    """Strict and immutable base for every external/process value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceBinding(FrozenModel):
    sha: GitObject
    tree: GitObject


class RootOwnedFile(FrozenModel):
    """Metadata only for one externally installed file; never its contents."""

    reference: Reference
    path: AbsolutePath
    owner: Literal["root"]
    group: Literal["ctower"]
    mode: FileMode
    sha256: Digest

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if not self.reference.startswith(
            ("file-ref://", "credential-file-ref://", "telemetry-ref://")
        ):
            raise ValueError("installed files require a file reference")
        _require_absolute_path(self.path, "installed file")
        return self


class OutputFile(FrozenModel):
    """A protected output target which need not exist before bootstrap."""

    reference: Reference
    path: AbsolutePath
    owner: Literal["root"]
    group: Literal["ctower"]
    mode: Literal["0400"]

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if not self.reference.startswith("file-ref://"):
            raise ValueError("bootstrap output requires a file reference")
        _require_absolute_path(self.path, "bootstrap output")
        return self


class DirectoryBinding(FrozenModel):
    reference: Reference
    path: AbsolutePath

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if not self.reference.startswith("object-root-ref://"):
            raise ValueError("object root requires an object-root reference")
        _require_absolute_path(self.path, "object root")
        return self


class ConfigArtifact(FrozenModel):
    path: RelativePath
    sha256: Digest


class ConfigurationBindings(FrozenModel):
    compose: ConfigArtifact
    caddyfile: ConfigArtifact
    otel_collector: ConfigArtifact

    def artifacts(self) -> tuple[ConfigArtifact, ...]:
        return (self.compose, self.caddyfile, self.otel_collector)


class ImageBindings(FrozenModel):
    control: ImageDigest
    postgres: ImageDigest
    postgres_major: Literal[17]
    edge: ImageDigest
    collector: ImageDigest


class TlsBindings(FrozenModel):
    certificate: RootOwnedFile
    private_key: RootOwnedFile


class DatabaseBindings(FrozenModel):
    postgres_admin_password: RootOwnedFile
    service_dsn: RootOwnedFile
    projection_dsn: RootOwnedFile
    migration_dsn: RootOwnedFile
    role_admin_dsn: RootOwnedFile

    def credentials(self) -> tuple[RootOwnedFile, ...]:
        return (
            self.postgres_admin_password,
            self.service_dsn,
            self.projection_dsn,
            self.migration_dsn,
            self.role_admin_dsn,
        )

    @model_validator(mode="after")
    def validate_distinct_credentials(self) -> Self:
        _require_distinct_files(self.credentials(), "database credentials")
        return self


class BootstrapBindings(FrozenModel):
    output: OutputFile


class ObjectBindings(FrozenModel):
    adapter: Literal["local_encrypted_filesystem"]
    root: DirectoryBinding
    key: RootOwnedFile


class TelemetryBindings(FrozenModel):
    exporter: RootOwnedFile
    alert_owner_ref: Reference

    @model_validator(mode="after")
    def validate_reference_types(self) -> Self:
        if not self.exporter.reference.startswith("telemetry-ref://"):
            raise ValueError("telemetry exporter requires a telemetry reference")
        if not self.alert_owner_ref.startswith("alert-owner-ref://"):
            raise ValueError("alert owner requires an alert-owner reference")
        return self


class WorkloadIdentities(FrozenModel):
    api: Reference
    worker: Reference
    migrator: Reference
    role_admin: Reference

    @model_validator(mode="after")
    def validate_distinct_identities(self) -> Self:
        values = (self.api, self.worker, self.migrator, self.role_admin)
        if any(not value.startswith("identity-ref://") for value in values):
            raise ValueError("workloads require identity references")
        if len(set(values)) != len(values):
            raise ValueError("privileged and service identities must be distinct")
        return self


class DeploymentBindings(FrozenModel):
    """Complete reference-only one-host development deployment declaration."""

    schema_: Literal["ctower.private-vps-deployment/v1"] = Field(alias="schema")
    deployment_id: Identifier
    source: SourceBinding
    assurance: Literal["development"]
    durability_policy: Literal["pending_only"]
    failure_domain_count: Literal[1]
    cp3d_qualified: Literal[False]
    data_classification: Literal["disposable_synthetic_non_sensitive"]
    authoritative_ctower_project_writer: Literal[False]
    accepted_write_rpo0_claim: Literal[False]
    bind_address: str
    images: ImageBindings
    configuration: ConfigurationBindings
    tls: TlsBindings
    database: DatabaseBindings
    bootstrap: BootstrapBindings
    objects: ObjectBindings
    telemetry: TelemetryBindings
    workload_identities: WorkloadIdentities

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        _require_private_address(self.bind_address)
        sensitive = (
            *self.database.credentials(),
            self.tls.private_key,
            self.objects.key,
            self.telemetry.exporter,
        )
        _require_distinct_files(sensitive, "privileged and service credentials")
        return self

    def referenced_files(self) -> tuple[RootOwnedFile, ...]:
        """Return every required installed file without exposing file contents."""
        return (
            self.tls.certificate,
            self.tls.private_key,
            *self.database.credentials(),
            self.objects.key,
            self.telemetry.exporter,
        )


class ArtifactFile(FrozenModel):
    artifact_id: Identifier
    kind: ArtifactKind
    path: RelativePath
    sha256: Digest


class EvidenceInputs(FrozenModel):
    source: SourceBinding
    control_image: ImageDigest
    configuration: ConfigurationBindings


class ScheduledOccurrence(FrozenModel):
    occurrence_id: Identifier
    schedule_ref: Reference
    scheduled_for: datetime
    working_day: date
    trigger: Literal["scheduled", "manual"]
    origin: Literal["routine_scheduler", "manual_cli"]
    result_artifact_id: Identifier
    scheduler_receipt_artifact_id: Identifier | None
    manual_command_ref: Reference | None


class EvidenceManifest(FrozenModel):
    """Evidence-root declaration whose artifacts are verified from exact bytes."""

    schema_: Literal["ctower.private-vps-evidence/v1"] = Field(alias="schema")
    evidence_id: Identifier
    claim: Claim
    assurance: Literal["development", "cp3d"]
    durability_policy: Literal["pending_only", "cutover_rpo0"]
    object_adapter: Literal["local_encrypted_filesystem", "external_s3"]
    key_adapter: Literal["local_file", "external_kms"]
    producer_ref: Reference
    verifier_ref: Reference
    deployment_manifest: ArtifactFile
    cp3d_manifest: ArtifactFile | None
    bound_inputs: EvidenceInputs
    artifacts: tuple[ArtifactFile, ...]
    occurrences: tuple[ScheduledOccurrence, ...]

    @model_validator(mode="after")
    def validate_identities(self) -> Self:
        _require_identity(self.producer_ref, "producer")
        _require_identity(self.verifier_ref, "verifier")
        if self.producer_ref == self.verifier_ref:
            raise ValueError("producer and verifier identities must be distinct")
        return self


class Cp3dManifest(FrozenModel):
    """Minimal separately verified CP3-D activation binding for I1-exit proof."""

    schema_: Literal["ctower.cp3d-activation/v1"] = Field(alias="schema")
    activation_id: Identifier
    source: SourceBinding
    deployment_manifest_sha256: Digest
    control_image: ImageDigest
    configuration: ConfigurationBindings
    assurance: Literal["cp3d"]
    durability_policy: Literal["cutover_rpo0"]
    failure_domain_count: int = Field(ge=2, le=16)
    cp3d_qualified: Literal[True]
    accepted_record_rpo_seconds: Literal[0]
    object_adapter: Literal["external_s3"]
    key_adapter: Literal["external_kms"]
    producer_ref: Reference
    verifier_ref: Reference
    verification_artifact: ArtifactFile

    @model_validator(mode="after")
    def validate_independence(self) -> Self:
        _require_identity(self.producer_ref, "CP3-D producer")
        _require_identity(self.verifier_ref, "CP3-D verifier")
        if self.producer_ref == self.verifier_ref:
            raise ValueError("CP3-D producer and verifier must be distinct")
        return self


class SchedulerReceipt(FrozenModel):
    schema_: Literal["ctower.scheduler-receipt/v1"] = Field(alias="schema")
    occurrence_id: Identifier
    schedule_ref: Reference
    scheduled_for: datetime
    source: Literal["routine_scheduler"]
    manual_command_ref: None


class ResultIssue(FrozenModel):
    code: Identifier
    field: str


class OperationResult(FrozenModel):
    """Stable machine-readable CLI result with no input values or secrets."""

    schema_: Literal["ctower.private-vps-result/v1"] = Field(alias="schema")
    operation: Literal["validate", "evidence-verify"]
    ok: bool
    code: Identifier
    claim: Claim | None = None
    artifact_count: int = Field(ge=0)
    qualifying_working_days: int = Field(ge=0)
    issues: tuple[ResultIssue, ...]


def _require_private_address(value: str) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError("bind address must be an IP address") from error
    networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fc00::/7"),
    )
    outside_private_networks = not any(address in item for item in networks)
    if address.is_unspecified or address.is_loopback or outside_private_networks:
        raise ValueError("bind address must be a non-local private IP address")


def _require_absolute_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path must be absolute without parent traversal")


def _require_distinct_files(files: tuple[RootOwnedFile, ...], label: str) -> None:
    if len({item.reference for item in files}) != len(files):
        raise ValueError(f"{label} must use distinct references")
    if len({item.path for item in files}) != len(files):
        raise ValueError(f"{label} must use distinct mounted files")


def _require_identity(value: str, label: str) -> None:
    if not value.startswith("identity-ref://"):
        raise ValueError(f"{label} requires an identity reference")
