"""Public fail-closed interface for CP3-D packet validation and rendering."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import ValidationError

from tools.cp3d_packet.manifest import build_manifest, encode_manifest
from tools.cp3d_packet.models import HostBinding, PacketBindings

__all__ = [
    "PacketError",
    "canonical_manifest",
    "load_bindings",
    "parse_bindings",
]

JsonObject = dict[str, Any]
MAX_BINDINGS_BYTES = 256_000
UNRESOLVED_MARKERS = ("CP3D_REQUIRED", "CHANGE_ME", "CHANGEME", "TODO", "${", "<required")
CREDENTIAL_KEYS = {
    "access_key",
    "api_key",
    "credential",
    "credential_value",
    "password",
    "passphrase",
    "private_key",
    "secret",
    "secret_key",
    "token",
}
CREDENTIAL_TEXT = re.compile(r"(?i)(?:password|passphrase|secret|token|access[_-]?key)\s*[:=]")


class PacketError(RuntimeError):
    """The source packet or an external binding failed closed."""


def load_bindings(path: Path) -> PacketBindings:
    """Read and validate one bounded JSON bindings document."""
    try:
        if path.is_symlink() or not path.is_file():
            raise PacketError("bindings path must be a regular non-symlink file")
        encoded = path.read_bytes()
        if len(encoded) > MAX_BINDINGS_BYTES:
            raise PacketError("bindings document exceeds the 256 KB limit")
        raw = json.loads(encoded)
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise PacketError("bindings document is not readable strict JSON") from error
    return parse_bindings(raw)


def parse_bindings(raw: object) -> PacketBindings:
    """Reject material and markers before strict Pydantic parsing."""
    if not isinstance(raw, dict):
        raise PacketError("bindings document must be a JSON object")
    _reject_credential_material(raw)
    _reject_unresolved_markers(raw)
    try:
        return PacketBindings.model_validate(raw)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(item) for item in finding['loc'])}: {finding['msg']}"
            for finding in error.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
        )
        raise PacketError(f"bindings validation failed: {details}") from error


def canonical_manifest(
    bindings: PacketBindings,
    compose_documents: dict[str, JsonObject],
) -> bytes:
    """Validate rendered Compose documents and return typed canonical bytes."""
    for role in ("primary", "standby"):
        document = compose_documents.get(role, {})
        if document:
            _validate_compose_document(role, document, bindings)
    manifest = build_manifest(bindings, compose_documents)
    encoded = encode_manifest(manifest)
    _reject_encoded_material(encoded)
    return encoded


def _validate_compose_document(
    role: str,
    document: JsonObject,
    bindings: PacketBindings,
) -> None:
    expected_host = bindings.primary if role == "primary" else bindings.standby
    expected_service = f"postgres-{role}"
    if document.get("name") != f"ctower-cp3d-{role}":
        raise PacketError(f"{role} Compose project name is not fixed")
    service = _compose_service(role, document, expected_service)
    if service.get("image") != bindings.postgres.image:
        raise PacketError(f"{role} Compose image does not match the pinned binding")
    if service.get("environment"):
        raise PacketError(f"{role} Compose environment/default credential fallback is forbidden")
    expected_values = {
        "network_mode": "host",
        "read_only": True,
        "restart": "no",
        "user": f"{bindings.postgres.uid}:{bindings.postgres.gid}",
    }
    if any(service.get(name) != value for name, value in expected_values.items()):
        raise PacketError(f"{role} Compose confinement invariants are missing")
    if "ports" in service or service.get("privileged"):
        raise PacketError(f"{role} Compose public port or privilege is forbidden")
    _validate_command(role, service.get("command"), expected_host, bindings)
    _validate_mounts(role, service.get("volumes"), expected_host)
    _reject_credential_material(document)
    _reject_unresolved_markers(document)


def _compose_service(
    role: str,
    document: JsonObject,
    expected_service: str,
) -> JsonObject:
    services = document.get("services")
    if not isinstance(services, dict) or set(services) != {expected_service}:
        raise PacketError(f"{role} Compose project must contain only {expected_service}")
    service = services[expected_service]
    if not isinstance(service, dict):
        raise PacketError(f"{role} Compose service is not an object")
    return cast("JsonObject", service)


def _validate_command(
    role: str,
    raw: object,
    host: HostBinding,
    bindings: PacketBindings,
) -> None:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise PacketError(f"{role} PostgreSQL command must be an explicit argument list")
    command = cast("list[str]", raw)
    required = {
        f"listen_addresses={host.private_ip}",
        "ssl=on",
        "synchronous_commit=remote_apply",
        "synchronous_standby_names=FIRST 1 (ctower_i1_ack)",
    }
    if role == "standby":
        required.update(
            {
                "hot_standby=on",
                "primary_slot_name=ctower_i1_ack",
                "application_name=ctower_i1_ack",
                f"host={bindings.primary.private_ip}",
            }
        )
    joined = "\n".join(command)
    if any(value not in joined for value in required):
        raise PacketError(f"{role} PostgreSQL replication/TLS command is incomplete")
    if "0.0.0.0" in joined or "listen_addresses=*" in joined:  # noqa: S104
        raise PacketError(f"{role} PostgreSQL public listener is forbidden")


def _validate_mounts(role: str, raw: object, host: HostBinding) -> None:
    if not isinstance(raw, list):
        raise PacketError(f"{role} root-owned mounts are missing")
    declared_sources = {
        item.get("source")
        for item in raw
        if isinstance(item, dict) and item.get("read_only") is True
    }
    expected_sources = {item.path for item in host.files()}
    if not expected_sources.issubset(declared_sources):
        raise PacketError(f"{role} root-owned reference mounts are incomplete")
    data_mounts = [
        item for item in raw if isinstance(item, dict) and item.get("source") == host.data_directory
    ]
    if len(data_mounts) != 1 or data_mounts[0].get("read_only") is True:
        raise PacketError(f"{role} PostgreSQL data mount is missing or read-only")


def _reject_credential_material(value: object, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        _reject_mapping_material(value, path)
        return
    if isinstance(value, list):
        _reject_list_material(value, path)
        return
    if isinstance(value, str):
        _reject_text_material(value)


def _reject_mapping_material(value: dict[object, object], path: tuple[str, ...]) -> None:
    for key, child in value.items():
        normalized = str(key).lower()
        if normalized in CREDENTIAL_KEYS or normalized.endswith("_value"):
            location = ".".join((*path, str(key)))
            raise PacketError(f"credential material key is forbidden at {location}")
        _reject_credential_material(child, (*path, str(key)))


def _reject_list_material(value: list[object], path: tuple[str, ...]) -> None:
    for index, child in enumerate(value):
        _reject_credential_material(child, (*path, str(index)))


def _reject_text_material(value: str) -> None:
    if "FORBIDDEN_INLINE_MATERIAL" in value or "-----BEGIN " in value:
        raise PacketError("credential material value is forbidden")
    if CREDENTIAL_TEXT.search(value):
        raise PacketError("credential assignment is forbidden")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise PacketError("credential-bearing URL is forbidden")


def _reject_unresolved_markers(value: object) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _reject_unresolved_markers(child)
        return
    if isinstance(value, list):
        for child in value:
            _reject_unresolved_markers(child)
        return
    if isinstance(value, str) and any(
        marker.lower() in value.lower() for marker in UNRESOLVED_MARKERS
    ):
        raise PacketError("unresolved operator marker is forbidden")


def _reject_encoded_material(encoded: bytes) -> None:
    text = encoded.decode("utf-8")
    _reject_credential_material(text)
    _reject_unresolved_markers(text)
