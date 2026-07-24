"""Canonical anchor, inventory, and isolated-restore integrity rules."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

__all__: tuple[str, ...] = ()

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_I1_SOURCES = {
    "ctower.root-supervisor.default": "root_supervisor_journal",
    "ctower.effect.default": "effect_journal",
    "ctower.provider.default": "provider_journal",
}


def canonical_digest(payload: object) -> str:
    """Hash Ctower's deterministic JSON subset."""

    encoded = json.dumps(
        _canonical(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def installation_identity_digest(
    *,
    installation_id: UUID,
    tenant_id: UUID,
    identity_ref: str,
    issued_at: datetime,
) -> str:
    """Bind every persisted installation-identity body field."""

    return canonical_digest(
        {
            "schema_id": "ctower.installation-identity/v1",
            "installation_id": str(installation_id),
            "tenant_id": str(tenant_id),
            "identity_ref": identity_ref,
            "issued_at": _canonical_timestamp(issued_at),
        }
    )


def backup_manifest_digest(
    *,
    backup_id: UUID,
    tenant_id: UUID,
    repository_ref: str,
    repository_object_version: str,
    base_backup_sha256: str,
    wal_start_lsn: str,
    wal_stop_lsn: str,
    logical_dump_sha256: str,
    object_manifest_sha256: str,
    migration_manifest_sha256: str,
    key_reference: str,
    key_version: str,
    pgbackrest_sha256: str,
    pg_dump_sha256: str,
    started_at: datetime,
    completed_at: datetime,
) -> str:
    """Bind one verified run's complete persisted backup manifest."""

    return canonical_digest(
        {
            "schema_id": "ctower.backup-manifest/v1",
            "backup_id": str(backup_id),
            "tenant_id": str(tenant_id),
            "repository_ref": repository_ref,
            "repository_object_version": repository_object_version,
            "base_backup_sha256": base_backup_sha256,
            "wal_start_lsn": wal_start_lsn,
            "wal_stop_lsn": wal_stop_lsn,
            "logical_dump_sha256": logical_dump_sha256,
            "object_manifest_sha256": object_manifest_sha256,
            "migration_manifest_sha256": migration_manifest_sha256,
            "key_reference": key_reference,
            "key_version": key_version,
            "pgbackrest_sha256": pgbackrest_sha256,
            "pg_dump_sha256": pg_dump_sha256,
            "started_at": _canonical_timestamp(started_at),
            "completed_at": _canonical_timestamp(completed_at),
        }
    )


def anchor_digest(
    previous_anchor: str | None,
    entries: Sequence[tuple[int, str]],
) -> str:
    """Hash one nonempty contiguous accepted prefix and its predecessor."""

    if not entries:
        raise ValueError("anchor requires at least one accepted command")
    positions = tuple(position for position, _root in entries)
    if positions != tuple(range(positions[0], positions[-1] + 1)):
        raise ValueError("anchor positions must be contiguous and ordered")
    for position, root in entries:
        if position < 1 or _DIGEST.fullmatch(root) is None:
            raise ValueError("anchor entry identity is malformed")
    if previous_anchor is not None and _DIGEST.fullmatch(previous_anchor) is None:
        raise ValueError("previous anchor digest is malformed")
    return canonical_digest(
        {
            "previous_anchor_sha256": previous_anchor,
            "entries": [
                {"acceptance_position": position, "command_root": root}
                for position, root in entries
            ],
        }
    )


def inventory_digest(payload: Mapping[str, object]) -> str:
    """Hash only the signed expected-source revision body."""

    omitted = {"revision_sha256", "signature", "object_key", "object_version"}
    return canonical_digest({key: value for key, value in payload.items() if key not in omitted})


def inventory_failures(
    sources: Sequence[Mapping[str, object]],
    *,
    reconciled_source_keys: frozenset[str],
) -> tuple[str, ...]:
    """Reject omissions, fake zero sources, and unreconciled active journals."""

    by_key: dict[str, Mapping[str, object]] = {}
    failures: list[str] = []
    for source in sources:
        key = source.get("source_key")
        if not isinstance(key, str) or key in by_key:
            failures.append("inventory-source-key-duplicate-or-malformed")
            continue
        by_key[key] = source
    if set(by_key) != set(_I1_SOURCES):
        failures.append("inventory-source-set-incomplete")
    for key, expected_kind in _I1_SOURCES.items():
        selected = by_key.get(key)
        if selected is None:
            continue
        if selected.get("source_kind") != expected_kind:
            failures.append(f"inventory-source-kind-mismatch:{key}")
        failures.extend(_source_failures(key, selected, reconciled_source_keys))
    return tuple(failures)


def _source_failures(
    key: str,
    source: Mapping[str, object],
    reconciled_source_keys: frozenset[str],
) -> tuple[str, ...]:
    activation = source.get("activation")
    if activation == "not_exercised":
        return _inactive_source_failures(key, source)
    if activation != "active":
        return (f"inventory-activation-invalid:{key}",)
    return _active_source_failures(key, source, reconciled_source_keys)


def _inactive_source_failures(
    key: str,
    source: Mapping[str, object],
) -> tuple[str, ...]:
    valid = (
        source.get("cursor_declaration") == "zero_source"
        and source.get("source_count") == 0
        and source.get("trust_root_ref") is None
        and source.get("trusted_cursor") is None
        and source.get("activation_event_ref") is None
    )
    return () if valid else (f"inventory-zero-source-invalid:{key}",)


def _active_source_failures(
    key: str,
    source: Mapping[str, object],
    reconciled_source_keys: frozenset[str],
) -> tuple[str, ...]:
    source_count = source.get("source_count")
    declared = (
        source.get("cursor_declaration") == "trusted_cursor"
        and isinstance(source_count, int)
        and source_count > 0
        and _nonempty(source.get("trust_root_ref"))
        and _nonempty(source.get("trusted_cursor"))
        and _nonempty(source.get("activation_event_ref"))
    )
    failures = [] if declared else [f"inventory-active-source-invalid:{key}"]
    if key not in reconciled_source_keys:
        failures.append(f"inventory-active-source-unreconciled:{key}")
    return tuple(failures)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("integrity timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        raise TypeError("integrity payloads do not admit floating point")
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("integrity payload keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    raise TypeError(f"unsupported integrity value: {type(value).__name__}")
