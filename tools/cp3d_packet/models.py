"""Strict boundary models for CP3-D operator bindings and review output."""

from __future__ import annotations

import ipaddress
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

__all__ = [
    "HostBinding",
    "PacketBindings",
    "RootOwnedFile",
    "TopologyManifest",
]

Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Reference = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(?:account|alert|credential-file|evidence|file|kms-key|principal|"
            r"signature|vault-key|window|workload)-ref://[A-Za-z0-9._~:/-]+$"
        )
    ),
]
PostgresImage = Annotated[
    str,
    StringConstraints(pattern=(r"^[A-Za-z0-9._/-]+/postgres:17(?:\.[0-9]+)?@sha256:[0-9a-f]{64}$")),
]
PrivateAddress = Annotated[str, StringConstraints(min_length=7, max_length=45)]
FileMode = Literal["0400", "0440"]


class FrozenModel(BaseModel):
    """Strict and immutable base for all packet boundary values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RootOwnedFile(FrozenModel):
    """Reference metadata for one externally installed root-owned file."""

    reference: Reference
    path: NonEmpty
    owner: Literal["root"]
    group: NonEmpty
    mode: FileMode
    sha256: Digest

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if not self.reference.startswith(("file-ref://", "credential-file-ref://")):
            raise ValueError("root-owned input requires a file reference")
        path = PurePosixPath(self.path)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("root-owned file path must be absolute without parent traversal")
        if not path.is_relative_to("/etc/ctower/cp3d"):
            raise ValueError("root-owned packet inputs must live below /etc/ctower/cp3d")
        return self


class HostBinding(FrozenModel):
    """One VPS placement and its externally installed PostgreSQL inputs."""

    provider: NonEmpty
    region: NonEmpty
    zone: NonEmpty
    host_id: NonEmpty
    failure_domain: NonEmpty
    operator_domain: NonEmpty
    private_ip: PrivateAddress
    data_directory: NonEmpty
    postgres_config: RootOwnedFile
    hba_config: RootOwnedFile
    tls_ca: RootOwnedFile
    tls_certificate: RootOwnedFile
    tls_key: RootOwnedFile
    replication_passfile: RootOwnedFile | None = None

    @model_validator(mode="after")
    def validate_private_placement(self) -> Self:
        address = ipaddress.ip_address(self.private_ip)
        private_networks = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("fc00::/7"),
        )
        if not any(address in network for network in private_networks):
            raise ValueError("host endpoint must be a non-local private IP address")
        data = PurePosixPath(self.data_directory)
        if not data.is_absolute() or ".." in data.parts:
            raise ValueError("PostgreSQL data directory must be an absolute path")
        return self

    def files(self) -> tuple[RootOwnedFile, ...]:
        """Return the complete declared root-owned input set."""
        required = (
            self.postgres_config,
            self.hba_config,
            self.tls_ca,
            self.tls_certificate,
            self.tls_key,
        )
        if self.replication_passfile is None:
            return required
        return (*required, self.replication_passfile)


class PostgresBinding(FrozenModel):
    """Pinned PostgreSQL 17 replication invariants."""

    image: PostgresImage
    uid: int = Field(gt=0, le=65535)
    gid: int = Field(gt=0, le=65535)
    port: Literal[5432]
    database: Literal["ctower"]
    replication_user: Literal["ctower_replication"]
    standby_application_name: Literal["ctower_i1_ack"]
    synchronous_commit: Literal["remote_apply"]


class WorkloadIdentities(FrozenModel):
    """Distinct workload identities; values are references, never credentials."""

    primary: Reference
    standby: Reference
    backup: Reference
    object: Reference
    anchor: Reference
    recovery: Reference

    @model_validator(mode="after")
    def validate_distinct(self) -> Self:
        values = (
            self.primary,
            self.standby,
            self.backup,
            self.object,
            self.anchor,
            self.recovery,
        )
        if len(set(values)) != len(values):
            raise ValueError("workload identities must be distinct")
        if any(not value.startswith("workload-ref://") for value in values):
            raise ValueError("workload identities require workload references")
        return self


class ObjectStoreBinding(FrozenModel):
    """Off-host object targets and retention declarations."""

    endpoint: NonEmpty
    account_reference: Reference
    region: NonEmpty
    backup_bucket: NonEmpty
    object_bucket: NonEmpty
    anchor_bucket: NonEmpty
    versioning: Literal[True]
    object_lock: Literal[True]
    retention_days: int = Field(ge=1, le=36500)

    @model_validator(mode="after")
    def validate_store(self) -> Self:
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("object endpoint must be credential-free HTTPS")
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("object endpoint cannot be local")
        if not self.account_reference.startswith("account-ref://"):
            raise ValueError("object account requires an account reference")
        buckets = (self.backup_bucket, self.object_bucket, self.anchor_bucket)
        if len(set(buckets)) != len(buckets):
            raise ValueError("backup, object, and anchor buckets must be distinct")
        return self


class KeyRecoveryBinding(FrozenModel):
    """Vault/KMS references and recovery ceremony ownership."""

    vault_endpoint: NonEmpty
    vault_key_reference: Reference
    kms_key_reference: Reference
    public_key_digest: Digest
    recovery_principal: Reference
    ceremony_owner: NonEmpty

    @model_validator(mode="after")
    def validate_vault(self) -> Self:
        parsed = urlsplit(self.vault_endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("vault endpoint must be credential-free HTTPS")
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("vault endpoint cannot be local")
        expected = (
            (self.vault_key_reference, "vault-key-ref://"),
            (self.kms_key_reference, "kms-key-ref://"),
            (self.recovery_principal, "principal-ref://"),
        )
        if any(not value.startswith(prefix) for value, prefix in expected):
            raise ValueError("key recovery inputs use the wrong reference type")
        return self


class AlertingBinding(FrozenModel):
    destination_reference: Reference
    owner: NonEmpty

    @model_validator(mode="after")
    def validate_destination(self) -> Self:
        if not self.destination_reference.startswith("alert-ref://"):
            raise ValueError("alert destination requires an alert reference")
        return self


class SignedEvidence(FrozenModel):
    reference: Reference
    digest: Digest
    signature_reference: Reference

    @model_validator(mode="after")
    def validate_reference_types(self) -> Self:
        if not self.reference.startswith("evidence-ref://"):
            raise ValueError("signed evidence requires an evidence reference")
        if not self.signature_reference.startswith("signature-ref://"):
            raise ValueError("signed evidence requires a signature reference")
        return self


class AckLatencyAcceptance(FrozenModel):
    maximum_milliseconds: int = Field(gt=0, le=60000)
    owner: NonEmpty
    evidence: SignedEvidence


class SignedEvidenceSet(FrozenModel):
    topology_review: SignedEvidence
    network_tls_review: SignedEvidence
    object_lock_review: SignedEvidence
    image_attestation: SignedEvidence


class PacketBindings(FrozenModel):
    """Complete external binding declaration for the source-only packet."""

    schema_: Literal["ctower.cp3d-bindings/v1"] = Field(alias="schema")
    binding_kind: Literal["synthetic_mechanics", "operator_bound"]
    packet_id: NonEmpty
    runtime_policy: Literal["pending_only"]
    validation_context: Literal["same_host_mechanics", "distinct_host_review"]
    postgres: PostgresBinding
    primary: HostBinding
    standby: HostBinding
    workload_identities: WorkloadIdentities
    object_store: ObjectStoreBinding
    key_recovery: KeyRecoveryBinding
    alerting: AlertingBinding
    destructive_drill_window: Reference
    ack_latency_acceptance: AckLatencyAcceptance
    signed_evidence: SignedEvidenceSet

    @model_validator(mode="after")
    def validate_topology(self) -> Self:
        _validate_distinct_topology(self.primary, self.standby)
        if self.primary.replication_passfile is not None:
            raise ValueError("primary must not receive a replication credential passfile")
        if self.standby.replication_passfile is None:
            raise ValueError("standby requires a root-owned replication passfile reference")
        _validate_file_set(self.primary, self.standby)
        if not self.destructive_drill_window.startswith("window-ref://"):
            raise ValueError("destructive drill window requires a window reference")
        if self.binding_kind == "operator_bound" and _contains_synthetic(
            self.model_dump(mode="json", by_alias=True)
        ):
            raise ValueError("operator-bound inputs cannot contain synthetic identifiers")
        return self


class ManifestFile(FrozenModel):
    role: Literal["primary", "standby"]
    purpose: NonEmpty
    reference: Reference
    owner: Literal["root"]
    group: NonEmpty
    mode: FileMode
    sha256: Digest


class ManifestHost(FrozenModel):
    provider: NonEmpty
    region: NonEmpty
    zone: NonEmpty
    host_id: NonEmpty
    failure_domain: NonEmpty
    operator_domain: NonEmpty
    private_endpoint: PrivateAddress


class ComposeEvidence(FrozenModel):
    primary_config_digest: Digest
    standby_config_digest: Digest
    renderer: Literal["docker-compose-config-json"]
    daemon_contact: Literal[False]


class TopologyManifest(FrozenModel):
    """Canonical, credential-free Review/CSO handoff."""

    schema_: Literal["ctower.cp3d-topology-manifest/v1"] = Field(alias="schema")
    packet_state: Literal["READY_FOR_OPERATOR_BINDING"]
    cp3d_qualified: Literal[False]
    external_evidence_claim: Literal["not_exercised"]
    product_runtime: Literal["not_in_packet"]
    packet_id: NonEmpty
    binding_kind: Literal["synthetic_mechanics", "operator_bound"]
    validation_context: Literal["same_host_mechanics", "distinct_host_review"]
    runtime_policy: Literal["pending_only"]
    postgres_image: PostgresImage
    standby_application_name: Literal["ctower_i1_ack"]
    synchronous_commit: Literal["remote_apply"]
    primary: ManifestHost
    standby: ManifestHost
    root_owned_files: tuple[ManifestFile, ...]
    workload_identities: WorkloadIdentities
    object_store: ObjectStoreBinding
    key_recovery: KeyRecoveryBinding
    alerting: AlertingBinding
    destructive_drill_window: Reference
    ack_latency_acceptance: AckLatencyAcceptance
    signed_evidence: SignedEvidenceSet
    compose: ComposeEvidence
    external_steps: tuple[NonEmpty, ...]


def _contains_synthetic(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_synthetic(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_synthetic(child) for child in value)
    return isinstance(value, str) and "synthetic" in value.lower()


def _validate_distinct_topology(primary: HostBinding, standby: HostBinding) -> None:
    distinct_pairs = {
        "host identities": (primary.host_id, standby.host_id),
        "private endpoints": (primary.private_ip, standby.private_ip),
        "failure domains": (primary.failure_domain, standby.failure_domain),
        "operator domains": (primary.operator_domain, standby.operator_domain),
    }
    repeated = [name for name, values in distinct_pairs.items() if values[0] == values[1]]
    if repeated:
        raise ValueError(f"primary and standby require distinct {', '.join(repeated)}")


def _validate_file_set(primary: HostBinding, standby: HostBinding) -> None:
    all_files = (*primary.files(), *standby.files())
    if len({item.path for item in all_files}) != len(all_files):
        raise ValueError("root-owned file paths must be distinct")
    if len({item.reference for item in all_files}) != len(all_files):
        raise ValueError("root-owned file references must be distinct")
