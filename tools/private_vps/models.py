"""Strict immutable models mirroring the authored private-VPS schemas."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Annotated, Literal, NoReturn

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

__all__ = [
    "ArtifactFile",
    "CheckArtifact",
    "Claim",
    "DeploymentBindings",
    "EvidenceManifest",
    "OperationResult",
    "RootOwnedDirectory",
    "RootOwnedFile",
    "ScheduledOccurrence",
    "SchedulerReceipt",
    "SyntheticResult",
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
_IPV4_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
_PRIVATE_IPV4_PATTERN = (
    rf"^(?:10\.{_IPV4_OCTET}\.{_IPV4_OCTET}\.{_IPV4_OCTET}|"
    rf"172\.(?:1[6-9]|2[0-9]|3[01])\.{_IPV4_OCTET}\.{_IPV4_OCTET}|"
    rf"192\.168\.{_IPV4_OCTET}\.{_IPV4_OCTET})$"
)
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
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$"),
]
AbsolutePath = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=300,
        pattern=r"^/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
PrivateIpv4 = Annotated[
    str,
    StringConstraints(pattern=_PRIVATE_IPV4_PATTERN),
]
FileMode = Literal["0400", "0440"]
Claim = Literal["development_rehearsal", "i1_exit"]
CheckKind = Literal[
    "tls_access",
    "database_bootstrap",
    "health_telemetry",
    "upgrade_rollback",
    "worker_restart",
    "host_reboot",
    "restore_report",
    "clean_install",
    "legacy_baseline",
]
ArtifactKind = Literal[
    "deployment_contract_validation",
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
ContentSchema = Literal[
    "ctower.private-vps-deployment/v1",
    "ctower.private-vps-check/v1",
    "ctower.private-vps-synthetic-result/v1",
    "ctower.private-vps-scheduler-receipt/v1",
]
DevelopmentProvenance = Literal["self_declared_development_reference"]
_DATE_PATTERN = (
    r"(?:(?:(?!0000)[0-9]{4})-(?:(?:01|03|05|07|08|10|12)-"
    r"(?:0[1-9]|[12][0-9]|3[01])|(?:04|06|09|11)-(?:0[1-9]|[12][0-9]|30)|"
    r"02-(?:0[1-9]|1[0-9]|2[0-8]))|(?:(?:[0-9]{2}(?:0[48]|[2468][048]|[13579][26]))|"
    r"(?:(?:0[48]|[2468][048]|[13579][26])00))-02-29)"
)
_TIMESTAMP_PATTERN = re.compile(
    rf"^{_DATE_PATTERN}"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
)


def _mathematical_integer(value: object) -> int:
    if isinstance(value, bool):
        _invalid_integer()
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    _invalid_integer()


def _invalid_integer() -> NoReturn:
    raise ValueError("value is not a mathematical integer")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("timestamp is outside the authored language")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("timestamp is outside the authored language") from error


MathematicalInteger = Annotated[int, BeforeValidator(_mathematical_integer)]
UserGroupId = Annotated[MathematicalInteger, Field(ge=10001, le=10001)]
UnixIdentity = Annotated[MathematicalInteger, Field(ge=0, le=65535)]
PostgresMajor = Annotated[MathematicalInteger, Field(ge=17, le=17)]
SingleFailureDomain = Annotated[MathematicalInteger, Field(ge=1, le=1)]
Timestamp = Annotated[datetime, BeforeValidator(_timestamp)]


class FrozenModel(BaseModel):
    """Strict and immutable base for every external/process value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceBinding(FrozenModel):
    sha: GitObject
    tree: GitObject


class RootOwnedFile(FrozenModel):
    """Metadata only for one externally installed file."""

    reference: Reference
    path: AbsolutePath
    owner: Literal["root"]
    group: Literal["ctower"]
    group_id: UserGroupId
    mode: FileMode
    sha256: Digest


class OutputFile(FrozenModel):
    """Final bootstrap output contract."""

    reference: Reference
    path: AbsolutePath
    owner: Literal["root"]
    group: Literal["ctower"]
    group_id: UserGroupId
    mode: Literal["0400"]


class RootOwnedDirectory(FrozenModel):
    path: AbsolutePath
    owner: Literal["root"]
    group: Literal["ctower"]
    group_id: UserGroupId
    mode: Literal["0750"]


class DirectoryBinding(FrozenModel):
    reference: Reference
    path: AbsolutePath


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
    postgres_major: PostgresMajor
    edge: ImageDigest
    collector: ImageDigest


class TlsBindings(FrozenModel):
    certificate: RootOwnedFile
    private_key: RootOwnedFile


class DatabaseBindings(FrozenModel):
    postgres_admin_password: RootOwnedFile
    api_dsn: RootOwnedFile
    worker_dsn: RootOwnedFile
    projection_dsn: RootOwnedFile
    migration_dsn: RootOwnedFile
    role_admin_dsn: RootOwnedFile

    def credentials(self) -> tuple[RootOwnedFile, ...]:
        return (
            self.postgres_admin_password,
            self.api_dsn,
            self.worker_dsn,
            self.projection_dsn,
            self.migration_dsn,
            self.role_admin_dsn,
        )


class BootstrapBindings(FrozenModel):
    parent: RootOwnedDirectory
    output: OutputFile


class ObjectBindings(FrozenModel):
    adapter: Literal["local_encrypted_filesystem"]
    root: DirectoryBinding
    api_key: RootOwnedFile
    worker_key: RootOwnedFile

    def keys(self) -> tuple[RootOwnedFile, ...]:
        return (self.api_key, self.worker_key)


class TelemetryBindings(FrozenModel):
    exporter: RootOwnedFile
    alert_owner_ref: Reference


class WorkloadIdentity(FrozenModel):
    reference: Reference
    uid: UnixIdentity
    gid: UnixIdentity


class WorkloadIdentities(FrozenModel):
    postgres: WorkloadIdentity
    role_admin: WorkloadIdentity
    migrator: WorkloadIdentity
    api: WorkloadIdentity
    worker: WorkloadIdentity
    collector: WorkloadIdentity
    edge: WorkloadIdentity

    def services(self) -> tuple[tuple[str, WorkloadIdentity], ...]:
        return (
            ("postgres", self.postgres),
            ("role-admin", self.role_admin),
            ("migrator", self.migrator),
            ("api", self.api),
            ("worker", self.worker),
            ("collector", self.collector),
            ("edge", self.edge),
        )


class DeploymentBindings(FrozenModel):
    """Complete reference-only one-host development deployment declaration."""

    schema_: Literal["ctower.private-vps-deployment/v1"] = Field(alias="schema")
    deployment_id: Identifier
    source: SourceBinding
    assurance: Literal["development"]
    durability_policy: Literal["pending_only"]
    failure_domain_count: SingleFailureDomain
    cp3d_qualified: Literal[False]
    data_classification: Literal["disposable_synthetic_non_sensitive"]
    authoritative_ctower_project_writer: Literal[False]
    accepted_write_rpo0_claim: Literal[False]
    bind_address: PrivateIpv4
    images: ImageBindings
    configuration: ConfigurationBindings
    tls: TlsBindings
    database: DatabaseBindings
    bootstrap: BootstrapBindings
    objects: ObjectBindings
    telemetry: TelemetryBindings
    workload_identities: WorkloadIdentities

    def referenced_files(self) -> tuple[RootOwnedFile, ...]:
        """Return every required installed file without exposing file contents."""
        return (
            self.tls.certificate,
            self.tls.private_key,
            *self.database.credentials(),
            *self.objects.keys(),
            self.telemetry.exporter,
        )


class ArtifactFile(FrozenModel):
    artifact_id: Identifier
    kind: ArtifactKind
    path: RelativePath
    sha256: Digest
    media_type: Literal["application/json"]
    content_schema: ContentSchema


class EvidenceInputs(FrozenModel):
    source: SourceBinding
    control_image: ImageDigest
    configuration: ConfigurationBindings


class ScheduledOccurrence(FrozenModel):
    occurrence_id: Identifier
    schedule_ref: Reference
    scheduled_for: Timestamp
    working_day: date
    trigger: Literal["scheduled"]
    origin: Literal["routine_scheduler_reference"]
    result_artifact_id: Identifier
    scheduler_receipt_artifact_id: Identifier
    manual_command_ref: None


class EvidenceManifest(FrozenModel):
    """Development-only evidence root; it cannot express an I1-exit claim."""

    schema_: Literal["ctower.private-vps-evidence/v1"] = Field(alias="schema")
    evidence_id: Identifier
    claim: Literal["development_rehearsal"]
    assurance: Literal["development"]
    durability_policy: Literal["pending_only"]
    object_adapter: Literal["local_encrypted_filesystem"]
    key_adapter: Literal["local_file"]
    provenance: DevelopmentProvenance
    schedule_ref: Reference
    calendar: Literal["weekday_mon_fri_utc"]
    window_start: date
    window_end: date
    deployment_manifest_artifact_id: Identifier
    bound_inputs: EvidenceInputs
    artifacts: Annotated[tuple[ArtifactFile, ...], Field(min_length=20, max_length=50)]
    occurrences: Annotated[
        tuple[ScheduledOccurrence, ...],
        Field(min_length=5, max_length=20),
    ]


class CheckArtifact(FrozenModel):
    schema_: Literal["ctower.private-vps-check/v1"] = Field(alias="schema")
    artifact_id: Identifier
    kind: CheckKind
    outcome: Literal["pass"]
    provenance: DevelopmentProvenance
    observed_at: Timestamp
    source: SourceBinding
    control_image: ImageDigest


class SyntheticResult(FrozenModel):
    schema_: Literal["ctower.private-vps-synthetic-result/v1"] = Field(alias="schema")
    occurrence_id: Identifier
    schedule_ref: Reference
    scheduled_for: Timestamp
    working_day: date
    outcome: Literal["pass"]
    provenance: DevelopmentProvenance
    source: SourceBinding
    control_image: ImageDigest


class SchedulerReceipt(FrozenModel):
    schema_: Literal["ctower.private-vps-scheduler-receipt/v1"] = Field(alias="schema")
    occurrence_id: Identifier
    schedule_ref: Reference
    scheduled_for: Timestamp
    working_day: date
    trigger: Literal["scheduled"]
    origin: Literal["routine_scheduler_reference"]
    provenance: DevelopmentProvenance
    source: SourceBinding
    control_image: ImageDigest
    manual_command_ref: None


class ResultIssue(FrozenModel):
    code: Identifier
    field: str


class OperationResult(FrozenModel):
    """Stable machine-readable CLI result with no input values or secrets."""

    schema_: Literal["ctower.private-vps-result/v1"] = Field(alias="schema")
    operation: Literal["arguments", "validate", "evidence-verify"]
    ok: bool
    code: Identifier
    claim: Claim | None = None
    artifact_count: int = Field(ge=0)
    qualifying_working_days: int = Field(ge=0)
    issues: tuple[ResultIssue, ...]
