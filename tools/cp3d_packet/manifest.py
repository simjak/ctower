"""Canonical redacted CP3-D topology manifest construction."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from tools.cp3d_packet.models import (
    ComposeEvidence,
    HostBinding,
    ManifestFile,
    ManifestHost,
    PacketBindings,
    TopologyManifest,
)

__all__ = ["build_manifest", "encode_manifest"]

JsonObject = dict[str, Any]
FILE_PURPOSES = (
    "postgres_config",
    "hba_config",
    "tls_ca",
    "tls_certificate",
    "tls_key",
    "replication_passfile",
)
EXTERNAL_STEPS = (
    "provider provisioning",
    "private network and firewall policy",
    "TLS issuance and installation",
    "credential installation",
    "promotion or accepted-write activation",
    "host poweroff drill",
    "isolated restore enablement",
    "cleanup",
)


def build_manifest(
    bindings: PacketBindings,
    compose_documents: dict[str, JsonObject],
) -> TopologyManifest:
    """Build the typed source-only manifest without local file paths or values."""
    return TopologyManifest(
        schema="ctower.cp3d-topology-manifest/v1",
        packet_state="READY_FOR_OPERATOR_BINDING",
        cp3d_qualified=False,
        external_evidence_claim="not_exercised",
        product_runtime="not_in_packet",
        packet_id=bindings.packet_id,
        binding_kind=bindings.binding_kind,
        validation_context=bindings.validation_context,
        runtime_policy=bindings.runtime_policy,
        postgres_image=bindings.postgres.image,
        standby_application_name=bindings.postgres.standby_application_name,
        synchronous_commit=bindings.postgres.synchronous_commit,
        primary=_manifest_host(bindings.primary),
        standby=_manifest_host(bindings.standby),
        root_owned_files=(
            *_manifest_files("primary", bindings.primary),
            *_manifest_files("standby", bindings.standby),
        ),
        workload_identities=bindings.workload_identities,
        object_store=bindings.object_store,
        key_recovery=bindings.key_recovery,
        alerting=bindings.alerting,
        destructive_drill_window=bindings.destructive_drill_window,
        ack_latency_acceptance=bindings.ack_latency_acceptance,
        signed_evidence=bindings.signed_evidence,
        compose=ComposeEvidence(
            primary_config_digest=_document_digest(compose_documents.get("primary", {})),
            standby_config_digest=_document_digest(compose_documents.get("standby", {})),
            renderer="docker-compose-config-json",
            daemon_contact=False,
        ),
        external_steps=EXTERNAL_STEPS,
    )


def encode_manifest(manifest: TopologyManifest) -> bytes:
    """Return newline-terminated canonical JSON bytes."""
    value = manifest.model_dump(mode="json", by_alias=True)
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _manifest_host(host: HostBinding) -> ManifestHost:
    return ManifestHost(
        provider=host.provider,
        region=host.region,
        zone=host.zone,
        host_id=host.host_id,
        failure_domain=host.failure_domain,
        operator_domain=host.operator_domain,
        private_endpoint=host.private_ip,
    )


def _manifest_files(
    role: Literal["primary", "standby"],
    host: HostBinding,
) -> tuple[ManifestFile, ...]:
    entries: list[ManifestFile] = []
    for purpose in FILE_PURPOSES:
        source = getattr(host, purpose)
        if source is None:
            continue
        entries.append(
            ManifestFile(
                role=role,
                purpose=purpose,
                reference=source.reference,
                owner=source.owner,
                group=source.group,
                mode=source.mode,
                sha256=source.sha256,
            )
        )
    return tuple(entries)


def _document_digest(document: JsonObject) -> str:
    encoded = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
