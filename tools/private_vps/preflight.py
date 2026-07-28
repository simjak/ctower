"""Read-only source, configuration, identity, and installed-file preflight."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tools.private_vps.compose_policy import verify_compose
from tools.private_vps.manifest import (
    MAX_COMPOSE_BYTES,
    MAX_CONFIGURATION_BYTES,
    MAX_DOCUMENT_BYTES,
    ConfinedRoot,
    FileSnapshot,
    PacketError,
    load_snapshot,
    verify_secret_free_text,
)
from tools.private_vps.models import (
    ConfigArtifact,
    DeploymentBindings,
    RootOwnedDirectory,
    RootOwnedFile,
)

__all__ = [
    "DirectoryObservation",
    "FileObservation",
    "validate_deployment",
    "verify_configuration",
    "verify_configuration_confined",
    "verify_deployment_authority",
]

_CONFIGURATION_PATHS = ("compose.yaml", "Caddyfile", "otel-collector.yaml")
_REFERENCE_PATHS = (
    "/run/ctower/refs/tls-certificate",
    "/run/ctower/refs/tls-private-key",
    "/run/ctower/refs/postgres-admin-password",
    "/run/ctower/refs/api-dsn",
    "/run/ctower/refs/worker-dsn",
    "/run/ctower/refs/projection-dsn",
    "/run/ctower/refs/migration-dsn",
    "/run/ctower/refs/role-admin-dsn",
    "/run/ctower/refs/api-object-key",
    "/run/ctower/refs/worker-object-key",
    "/run/ctower/refs/telemetry-exporter",
)
_REFERENCE_NAMES = (
    "file-ref://private-vps/tls-certificate",
    "credential-file-ref://private-vps/tls-private-key",
    "credential-file-ref://private-vps/postgres-admin-password",
    "credential-file-ref://private-vps/api-dsn",
    "credential-file-ref://private-vps/worker-dsn",
    "credential-file-ref://private-vps/projection-dsn",
    "credential-file-ref://private-vps/migration-dsn",
    "credential-file-ref://private-vps/role-admin-dsn",
    "credential-file-ref://private-vps/api-object-key",
    "credential-file-ref://private-vps/worker-object-key",
    "telemetry-ref://private-vps/exporter",
)
_IDENTITIES = {
    "postgres": (999, 10001),
    "role-admin": (0, 10001),
    "migrator": (10001, 10001),
    "api": (10001, 10001),
    "worker": (10002, 10001),
    "collector": (10003, 10001),
    "edge": (10004, 10001),
}
_IPV4_VERSION = 4
_CONFIGURATION_REVISION = "ctower.private-vps-effective-configuration/v1"
_SEALED_EFFECTIVE_CONFIGURATION = {
    (
        "deploy/private-vps/development/Caddyfile",
        _CONFIGURATION_REVISION,
    ): "sha256:f563133e6cb9f600e89da6c1f1cecf3c806049dafcbaaf5e2c9f2edd4045f4ad",
    (
        "deploy/private-vps/development/otel-collector.yaml",
        _CONFIGURATION_REVISION,
    ): "sha256:a735d2a553736df537851255896abc515e73e645aa66f2853cead01f3a76df9c",
}


@dataclass(frozen=True, slots=True)
class FileObservation:
    regular: bool
    owner_uid: int
    owner_gid: int
    mode: str
    sha256: str


@dataclass(frozen=True, slots=True)
class DirectoryObservation:
    owner_uid: int
    owner_gid: int
    mode: str


def validate_deployment(
    path: Path,
    expected_source_sha: str,
    expected_source_tree: str,
    *,
    observer: Callable[[RootOwnedFile], FileObservation] | None = None,
    directory_observer: Callable[[RootOwnedDirectory], DirectoryObservation] | None = None,
) -> DeploymentBindings:
    """Validate one exact, development-only deployment declaration."""
    absolute = path.absolute()
    with ConfinedRoot(absolute.parent) as packet_root:
        snapshot = packet_root.read(
            absolute.name,
            field="bindings",
            max_bytes=MAX_DOCUMENT_BYTES,
        )
        bindings = load_snapshot(snapshot, DeploymentBindings, field="bindings")
        _verify_source(bindings, expected_source_sha, expected_source_tree)
        verify_configuration_confined(bindings, packet_root, prefix="")
    inspect = observer or observe_file
    for index, reference in enumerate(bindings.referenced_files()):
        _validate_file(reference, inspect(reference), field=f"references.{index}")
    inspect_directory = directory_observer or observe_directory
    _validate_directory(
        bindings.bootstrap.parent,
        inspect_directory(bindings.bootstrap.parent),
        field="bootstrap.parent",
    )
    return bindings


def verify_configuration(bindings: DeploymentBindings, base: Path) -> None:
    """Verify exact bound configuration snapshots beneath one safe root."""
    with ConfinedRoot(base) as root:
        verify_configuration_confined(bindings, root, prefix="")


def observe_file(reference: RootOwnedFile) -> FileObservation:
    """Observe installed bytes and UID/GID metadata without following symlinks."""
    with ConfinedRoot(Path("/")) as root:
        snapshot = root.read(
            reference.path.removeprefix("/"),
            field="references",
            max_bytes=MAX_CONFIGURATION_BYTES,
        )
    return FileObservation(
        regular=True,
        owner_uid=snapshot.owner_uid,
        owner_gid=snapshot.owner_gid,
        mode=snapshot.mode,
        sha256=snapshot.sha256,
    )


def observe_directory(reference: RootOwnedDirectory) -> DirectoryObservation:
    """Observe the bootstrap parent from a descriptor-confined root."""
    with ConfinedRoot(Path("/")) as root:
        snapshot = root.directory(
            reference.path.removeprefix("/"),
            field="bootstrap.parent",
        )
    return DirectoryObservation(
        owner_uid=snapshot.owner_uid,
        owner_gid=snapshot.owner_gid,
        mode=snapshot.mode,
    )


def verify_configuration_confined(
    bindings: DeploymentBindings,
    root: ConfinedRoot,
    *,
    prefix: str,
) -> None:
    verify_deployment_authority(bindings)
    artifacts = bindings.configuration.artifacts()
    if tuple(artifact.path for artifact in artifacts) != _CONFIGURATION_PATHS:
        raise PacketError("configuration_path_changed", "configuration")
    compose_snapshot = None
    for index, artifact in enumerate(artifacts):
        maximum = MAX_COMPOSE_BYTES if index == 0 else MAX_CONFIGURATION_BYTES
        snapshot = root.read(
            _join(prefix, artifact.path),
            field=f"configuration.{index}",
            max_bytes=maximum,
        )
        if snapshot.sha256 != artifact.sha256:
            raise PacketError("configuration_changed", f"configuration.{index}.sha256")
        if index == 0:
            compose_snapshot = snapshot
        else:
            _verify_effective_configuration(artifact, snapshot, index=index)
    if compose_snapshot is None:
        raise PacketError("invalid_compose", "configuration.compose")
    verify_compose(compose_snapshot, bindings)


def verify_deployment_authority(bindings: DeploymentBindings) -> None:
    """Enforce the one exact source-packet deployment authority."""
    _verify_bind_address(bindings.bind_address)
    _verify_paths(bindings)
    _verify_identities(bindings)


def _verify_source(bindings: DeploymentBindings, sha: str, tree: str) -> None:
    if bindings.source.sha != sha:
        raise PacketError("source_changed", "source.sha")
    if bindings.source.tree != tree:
        raise PacketError("source_changed", "source.tree")


def _verify_effective_configuration(
    artifact: ConfigArtifact,
    snapshot: FileSnapshot,
    *,
    index: int,
) -> None:
    source_path = f"deploy/private-vps/development/{artifact.path}"
    expected = _SEALED_EFFECTIVE_CONFIGURATION.get((source_path, _CONFIGURATION_REVISION))
    field = f"configuration.{index}"
    if expected is None or artifact.sha256 != expected or snapshot.sha256 != expected:
        raise PacketError("effective_configuration_changed", field)
    verify_secret_free_text(snapshot, field=field)


def _verify_bind_address(raw: str) -> None:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as error:
        raise PacketError("unsafe_bind_address", "bind_address") from error
    if address.version != _IPV4_VERSION or not address.is_private or address.is_loopback:
        raise PacketError("unsafe_bind_address", "bind_address")


def _verify_paths(bindings: DeploymentBindings) -> None:
    files = bindings.referenced_files()
    if tuple(item.path for item in files) != _REFERENCE_PATHS:
        raise PacketError("reference_path_changed", "references")
    if tuple(item.reference for item in files) != _REFERENCE_NAMES:
        raise PacketError("reference_changed", "references")
    if bindings.bootstrap.parent.path != "/run/ctower/bootstrap":
        raise PacketError("bootstrap_path_changed", "bootstrap.parent")
    if bindings.bootstrap.output.path != "/run/ctower/bootstrap/first-tenant.json":
        raise PacketError("bootstrap_path_changed", "bootstrap.output")
    if bindings.objects.root.path != "/var/lib/ctower/objects":
        raise PacketError("object_path_changed", "objects.root")
    if bindings.objects.root.reference != "object-root-ref://private-vps/development":
        raise PacketError("object_reference_changed", "objects.root")
    if bindings.bootstrap.output.reference != "file-ref://private-vps/bootstrap-output":
        raise PacketError("bootstrap_reference_changed", "bootstrap.output")
    if bindings.telemetry.alert_owner_ref != "alert-owner-ref://private-vps/development":
        raise PacketError("alert_owner_changed", "telemetry.alert_owner_ref")


def _verify_identities(bindings: DeploymentBindings) -> None:
    services = bindings.workload_identities.services()
    if len({identity.reference for _, identity in services}) != len(services):
        raise PacketError("duplicate_identity", "workload_identities")
    for name, identity in services:
        if identity.reference != f"identity-ref://private-vps/{name}":
            raise PacketError("identity_reference_changed", f"workload_identities.{name}")
        if (identity.uid, identity.gid) != _IDENTITIES[name]:
            raise PacketError("identity_changed", f"workload_identities.{name}")


def _validate_file(
    reference: RootOwnedFile,
    observed: FileObservation,
    *,
    field: str,
) -> None:
    if not observed.regular:
        raise PacketError("unsafe_reference_type", field)
    if observed.owner_uid != 0 or observed.owner_gid != reference.group_id:
        raise PacketError("unsafe_reference_owner", field)
    if observed.mode != reference.mode:
        raise PacketError("unsafe_reference_permissions", field)
    if observed.sha256 != reference.sha256:
        raise PacketError("reference_changed", field)


def _validate_directory(
    reference: RootOwnedDirectory,
    observed: DirectoryObservation,
    *,
    field: str,
) -> None:
    if observed.owner_uid != 0 or observed.owner_gid != reference.group_id:
        raise PacketError("unsafe_output_owner", field)
    if observed.mode != reference.mode:
        raise PacketError("unsafe_output_permissions", field)


def _join(prefix: str, relative: str) -> str:
    if not prefix:
        return relative
    return (PurePosixPath(prefix) / relative).as_posix()
