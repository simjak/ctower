"""Read-only source, configuration, and installed-reference preflight."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from tools.private_vps.manifest import PacketError, digest_file, load_model, resolve_artifact
from tools.private_vps.models import DeploymentBindings, RootOwnedFile

__all__ = ["FileObservation", "validate_deployment", "verify_configuration"]


@dataclass(frozen=True, slots=True)
class FileObservation:
    regular: bool
    owner_uid: int
    mode: str
    sha256: str


def validate_deployment(
    path: Path,
    expected_source_sha: str,
    expected_source_tree: str,
    *,
    observer: Callable[[RootOwnedFile], FileObservation] | None = None,
) -> DeploymentBindings:
    """Validate exact source/config bytes and root-owned reference metadata."""
    bindings = load_model(path, DeploymentBindings, field="bindings")
    if bindings.source.sha != expected_source_sha:
        raise PacketError("source_changed", "source.sha")
    if bindings.source.tree != expected_source_tree:
        raise PacketError("source_changed", "source.tree")
    verify_configuration(bindings, path.parent)
    inspect = observer or observe_file
    for index, reference in enumerate(bindings.referenced_files()):
        _validate_file(reference, inspect(reference), field=f"references.{index}")
    _validate_output_parent(bindings.bootstrap.output.path)
    return bindings


def verify_configuration(bindings: DeploymentBindings, base: Path) -> None:
    """Verify bound config digests and Compose isolation without daemon access."""
    for index, artifact in enumerate(bindings.configuration.artifacts()):
        path = resolve_artifact(base, artifact.path, field=f"configuration.{index}.path")
        observed = digest_file(path, field=f"configuration.{index}")
        if observed != artifact.sha256:
            raise PacketError("configuration_changed", f"configuration.{index}.sha256")
    _verify_compose(bindings, base)


def observe_file(reference: RootOwnedFile) -> FileObservation:
    """Observe only metadata and a digest; never return installed file bytes."""
    path = Path(reference.path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise PacketError("missing_or_unsafe_reference", "references") from error
    try:
        digest = hashlib.sha256()
        while block := os.read(descriptor, 64 * 1024):
            digest.update(block)
    except OSError as error:
        raise PacketError("unreadable_reference", "references") from error
    finally:
        os.close(descriptor)
    return FileObservation(
        regular=stat.S_ISREG(metadata.st_mode),
        owner_uid=metadata.st_uid,
        mode=f"{stat.S_IMODE(metadata.st_mode):04o}",
        sha256=f"sha256:{digest.hexdigest()}",
    )


def _validate_file(reference: RootOwnedFile, observed: FileObservation, *, field: str) -> None:
    if not observed.regular:
        raise PacketError("unsafe_reference_type", field)
    if observed.owner_uid != 0:
        raise PacketError("unsafe_reference_owner", field)
    if observed.mode != reference.mode:
        raise PacketError("unsafe_reference_permissions", field)
    if observed.sha256 != reference.sha256:
        raise PacketError("reference_changed", field)


def _validate_output_parent(raw_path: str) -> None:
    parent = Path(raw_path).parent
    try:
        metadata = parent.lstat()
    except OSError as error:
        raise PacketError("missing_output_parent", "bootstrap.output") from error
    if parent.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise PacketError("unsafe_output_parent", "bootstrap.output")
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise PacketError("unsafe_output_permissions", "bootstrap.output")


def _verify_compose(bindings: DeploymentBindings, base: Path) -> None:
    path = resolve_artifact(
        base,
        bindings.configuration.compose.path,
        field="configuration.compose.path",
    )
    try:
        raw = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, YAMLError) as error:
        raise PacketError("invalid_compose", "configuration.compose") from error
    document = _mapping(raw, "configuration.compose")
    services = _mapping(document.get("services"), "configuration.compose.services")
    _verify_images(bindings, services)
    _verify_host_exposure(services)
    postgres = _mapping(services.get("postgres"), "configuration.compose.services.postgres")
    if postgres.get("networks") != ["record"]:
        raise PacketError("postgres_network_changed", "configuration.compose.services.postgres")
    edge = _mapping(services.get("edge"), "configuration.compose.services.edge")
    expected_port = f"{bindings.bind_address}:443:443"
    if edge.get("ports") != [expected_port]:
        raise PacketError("edge_bind_changed", "configuration.compose.services.edge.ports")
    networks = _mapping(document.get("networks"), "configuration.compose.networks")
    record = _mapping(networks.get("record"), "configuration.compose.networks.record")
    if record.get("internal") is not True:
        raise PacketError("postgres_network_not_internal", "configuration.compose.networks.record")


def _verify_host_exposure(services: dict[str, Any]) -> None:
    for name, raw in services.items():
        service = _mapping(raw, f"configuration.compose.services.{name}")
        if name != "edge" and (service.get("ports") or service.get("network_mode") == "host"):
            code = "postgres_host_exposure" if name == "postgres" else "non_edge_host_exposure"
            raise PacketError(code, f"configuration.compose.services.{name}")


def _verify_images(bindings: DeploymentBindings, services: dict[str, Any]) -> None:
    expected = {
        "api": bindings.images.control,
        "worker": bindings.images.control,
        "migrator": bindings.images.control,
        "role-admin": bindings.images.control,
        "postgres": bindings.images.postgres,
        "edge": bindings.images.edge,
        "collector": bindings.images.collector,
    }
    for name, image in expected.items():
        service = _mapping(services.get(name), f"configuration.compose.services.{name}")
        if service.get("image") != image:
            field = f"configuration.compose.services.{name}.image"
            raise PacketError("image_binding_changed", field)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PacketError("invalid_compose", field)
    return cast("dict[str, Any]", value)
