"""Reviewed selection verification and deterministic canonical export."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from .canonical import (
    JsonValue,
    artifact_digest,
    canonical_bytes,
    canonical_digest,
    validate_contract,
)
from .refusal import MigrationRefusal, RefusalCode
from .signing import ArtifactSigner, ArtifactVerifier
from .source import (
    PositionedRecord,
    ReadOnlySourceRoot,
    SourceRecord,
    parse_jsonl,
    validate_relative_path,
)

__all__ = (
    "EXPORT_A",
    "EXPORT_B",
    "FrozenExport",
    "compare_exports",
    "equality_manifest_bytes",
    "freeze_export",
    "verify_selection",
)

_EXPORT_NAMESPACE = UUID("7531dc77-43d1-5127-a665-804c74c18786")
EXPORT_A: Literal["export_a"] = "export_a"
EXPORT_B: Literal["export_b"] = "export_b"
_SOURCE_KEYS = {
    "mission_control_requests",
    "mission_control_tasks",
    "mission_control_project",
    "mission_control_decisions",
    "mission_control_coordination",
    "git_ctower",
    "github_ctower",
    "ctower_target",
}
_DIMENSIONS = (
    "logical_identities",
    "physical_slice_digests",
    "counts",
    "byte_ranges",
    "native_watermarks",
    "file_identities",
    "last_complete_offsets",
    "path_manifest",
    "git_refs_and_objects",
    "github_nodes_and_checks",
    "expected_zero_sources",
    "target_inventory",
    "semantic_export",
)


@dataclass(frozen=True)
class FrozenExport:
    manifest: dict[str, Any]
    semantic_bytes: bytes
    records: tuple[SourceRecord, ...]


def verify_selection(selection: Mapping[str, Any], verifier: ArtifactVerifier) -> str:
    inventories = selection.get("source_inventories")
    if isinstance(inventories, list):
        for inventory in inventories:
            if isinstance(inventory, dict) and isinstance(inventory.get("path"), str):
                validate_relative_path(inventory["path"])
    validate_contract("ctower-project-source-selection.schema.json", selection)
    digest = verifier.verify(selection, "manifest_digest")
    review = selection.get("review")
    if not isinstance(review, dict) or review.get("decision") != "approved":
        raise MigrationRefusal(RefusalCode.UNREVIEWED_CANDIDATE, "source selection review")
    return digest


def freeze_export(
    selection: Mapping[str, Any],
    root: ReadOnlySourceRoot,
    target_inventory: Mapping[str, Any],
    *,
    cutover_id: UUID,
    export_stage: Literal["export_a", "export_b"],
    verifier: ArtifactVerifier,
) -> FrozenExport:
    selection_digest = verify_selection(selection, verifier)
    _verify_target_inventory(target_inventory)
    source_manifests: list[dict[str, Any]] = []
    path_entries: list[dict[str, JsonValue]] = []
    semantic_records: list[dict[str, JsonValue]] = []
    selected_records: list[SourceRecord] = []
    inventories = cast(list[dict[str, Any]], selection["source_inventories"])
    if {str(item["source_key"]) for item in inventories} != _SOURCE_KEYS:
        raise MigrationRefusal(RefusalCode.SOURCE_SELECTION_DRIFT, "source inventory keys")
    for inventory in sorted(inventories, key=lambda item: str(item["source_key"])):
        source, paths, semantic, records = _freeze_source(selection, root, inventory)
        source_manifests.append(source)
        path_entries.append(paths)
        semantic_records.extend(semantic)
        selected_records.extend(records)
    semantic_records.sort(key=_semantic_sort_key)
    semantic_bytes = canonical_bytes(cast(JsonValue, semantic_records))
    path_digest = canonical_digest(cast(JsonValue, path_entries))
    export_digest = canonical_digest(cast(JsonValue, semantic_records))
    created_at = str(selection["created_at"])
    manifest: dict[str, Any] = {
        "schema": "ctower.ctower-project-export-manifest/v1",
        "export_id": str(
            uuid5(_EXPORT_NAMESPACE, f"{cutover_id}:{selection_digest}:{export_stage}")
        ),
        "cutover_id": str(cutover_id),
        "exporter_pass": export_stage,
        "selection_digest": selection_digest,
        "created_at": created_at,
        "canonicalization": "RFC8785",
        "sources": source_manifests,
        "target_inventory": dict(target_inventory),
        "path_manifest_digest": path_digest,
        "semantic_export_digest": export_digest,
    }
    manifest["artifact_digest"] = artifact_digest(manifest, "artifact_digest")
    validate_contract("ctower-project-export-manifest.schema.json", manifest)
    return FrozenExport(manifest, semantic_bytes, tuple(selected_records))


def compare_exports(
    export_a: FrozenExport,
    export_b: FrozenExport,
    *,
    review: Mapping[str, Any],
    signer: ArtifactSigner,
) -> dict[str, Any]:
    first = export_a.manifest
    second = export_b.manifest
    if first["exporter_pass"] != EXPORT_A or second["exporter_pass"] != EXPORT_B:
        raise MigrationRefusal(RefusalCode.EXPORT_NONDETERMINISM, "export pass binding")
    mismatches = _mismatches(first, second, export_a.semantic_bytes, export_b.semantic_bytes)
    if mismatches:
        drift_code = (
            RefusalCode.SOURCE_SELECTION_DRIFT
            if "selection_digest" in mismatches
            else RefusalCode.EXPORT_NONDETERMINISM
        )
        raise MigrationRefusal(drift_code, ",".join(mismatches))
    cutover_id = str(first["cutover_id"])
    equality: dict[str, Any] = {
        "schema": "ctower.ctower-project-export-equality/v1",
        "equality_id": str(
            uuid5(
                _EXPORT_NAMESPACE,
                f"equality:{cutover_id}:{first['semantic_export_digest']}",
            )
        ),
        "cutover_id": cutover_id,
        "selection_digest": first["selection_digest"],
        "export_a_digest": first["artifact_digest"],
        "export_b_digest": second["artifact_digest"],
        "result": "equal",
        "compared_dimensions": list(_DIMENSIONS),
        "mismatches": [],
        "review": dict(review),
    }
    equality = signer.seal(equality, "report_digest")
    validate_contract("ctower-project-export-equality.schema.json", equality)
    return equality


def equality_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Canonical compared manifest, excluding three contract-required pass-local fields."""
    projection = {
        key: value
        for key, value in manifest.items()
        if key not in {"export_id", "exporter_pass", "artifact_digest"}
    }
    return canonical_bytes(cast(JsonValue, projection))


def _freeze_source(
    selection: Mapping[str, Any],
    root: ReadOnlySourceRoot,
    inventory: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, JsonValue], list[dict[str, JsonValue]], list[SourceRecord]]:
    path = inventory["path"]
    if path is None:
        if not bool(inventory["expected_zero"]):
            raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, str(inventory["source_key"]))
        return _empty_source(inventory), _empty_path_entry(inventory), [], []
    if not isinstance(path, str):
        raise MigrationRefusal(RefusalCode.CONTRACT_INVALID, "source inventory path")
    snapshot = root.read(path)
    records = parse_jsonl(snapshot)
    if (
        snapshot.digest != inventory["whole_source_digest"]
        or len(snapshot.data) != inventory["whole_source_bytes"]
        or len(records) != inventory["whole_source_rows"]
    ):
        raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, str(inventory["source_key"]))
    included = _reviewed_records(selection, records)
    grouped = _group_positions(included)
    if (
        len(grouped) != inventory["selected_logical_items"]
        or len(included) != inventory["selected_physical_items"]
        or bool(inventory["expected_zero"]) != (not included)
    ):
        raise MigrationRefusal(RefusalCode.SOURCE_SELECTION_DRIFT, str(inventory["source_key"]))
    selected_items, semantic = _selected_items(grouped)
    source = {
        "source_key": inventory["source_key"],
        "file_identity": {"device": snapshot.device, "inode": snapshot.inode},
        "watermark": inventory["watermark"],
        "last_complete_offset": len(snapshot.data),
        "logical_count": len(grouped),
        "physical_count": len(included),
        "content_digest": snapshot.digest,
        "selected_items": selected_items,
    }
    path_entry: dict[str, JsonValue] = {
        "source_key": cast(str, inventory["source_key"]),
        "path": path,
        "content_digest": snapshot.digest,
        "bytes": len(snapshot.data),
        "rows": len(records),
        "device": snapshot.device,
        "inode": snapshot.inode,
    }
    return source, path_entry, semantic, [item.record for item in included]


def _reviewed_records(
    selection: Mapping[str, Any], records: tuple[PositionedRecord, ...]
) -> tuple[PositionedRecord, ...]:
    included: list[PositionedRecord] = []
    forbidden = set(cast(list[str], selection["forbidden_classes"]))
    exclusions = {
        str(item["source_id"])
        for item in cast(list[dict[str, Any]], selection["explicit_exclusions"])
    }
    for positioned in records:
        record = positioned.record
        if forbidden.intersection(record.data_classes):
            raise MigrationRefusal(RefusalCode.FORBIDDEN_DATA_CLASS, "reviewed source row")
        if record.candidate and record.review_decision is None:
            raise MigrationRefusal(RefusalCode.UNREVIEWED_CANDIDATE, "candidate row")
        if record.review_decision == "excluded":
            if record.identity.immutable_source_id not in exclusions:
                raise MigrationRefusal(RefusalCode.OUTSIDE_REVIEWED_CLOSURE, "unbound exclusion")
            continue
        if record.review_decision == "included":
            _enforce_closure(selection, record)
            included.append(positioned)
    return tuple(included)


def _enforce_closure(selection: Mapping[str, Any], record: SourceRecord) -> None:
    identity = record.identity
    enumerated = {
        "stable-backlog": set(cast(list[str], selection["stable_item_ids"])),
        "mission-control:request": set(cast(list[str], selection["selected_request_ids"])),
        "mission-control:task": set(cast(list[str], selection["selected_task_ids"])),
        "catalog:ctower:checkpoint": set(cast(list[str], selection["checkpoint_keys"])),
    }
    allowed_open = {
        "mission-control:decision",
        "mission-control:coordination",
        "git:github.com/simjak/ctower:commit",
        "github:simjak/ctower:issue",
        "github:simjak/ctower:pull-request",
        "github:simjak/ctower:review",
        "github:simjak/ctower:check-run",
        "github:simjak/ctower:release",
    }
    if identity.namespace in enumerated:
        valid = identity.immutable_source_id in enumerated[identity.namespace]
    else:
        valid = identity.namespace in allowed_open
    if not valid:
        raise MigrationRefusal(RefusalCode.OUTSIDE_REVIEWED_CLOSURE, "included identity")


def _group_positions(
    included: tuple[PositionedRecord, ...],
) -> dict[tuple[str, str, str], list[PositionedRecord]]:
    grouped: dict[tuple[str, str, str], list[PositionedRecord]] = defaultdict(list)
    for item in included:
        grouped[item.record.identity.key()].append(item)
    return grouped


def _selected_items(
    grouped: Mapping[tuple[str, str, str], list[PositionedRecord]],
) -> tuple[list[dict[str, Any]], list[dict[str, JsonValue]]]:
    selected: list[dict[str, Any]] = []
    semantic: list[dict[str, JsonValue]] = []
    for key in sorted(grouped):
        positioned = grouped[key]
        identity = positioned[-1].record.identity.model_dump(mode="json")
        positions = [
            {
                "path": item.path,
                "line_number": item.line_number,
                "byte_start": item.byte_start,
                "byte_end": item.byte_end,
                "slice_digest": item.slice_digest,
            }
            for item in positioned
        ]
        selected.append({"identity": identity, "positions": positions})
        semantic.append(
            cast(
                dict[str, JsonValue],
                positioned[-1].record.model_dump(mode="json", by_alias=True),
            )
        )
    return selected, semantic


def _verify_target_inventory(target: Mapping[str, Any]) -> None:
    digest = target.get("inventory_digest")
    if digest != artifact_digest(target, "inventory_digest"):
        raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, "target inventory digest")
    if set(cast(list[str], target.get("explicit_zero_sources", []))) != {
        "root_supervisor",
        "effect_provider",
        "runtime_provider",
    }:
        raise MigrationRefusal(RefusalCode.SOURCE_SELECTION_DRIFT, "target zero sources")


def _empty_source(inventory: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_key": inventory["source_key"],
        "file_identity": None,
        "watermark": inventory["watermark"],
        "last_complete_offset": 0,
        "logical_count": 0,
        "physical_count": 0,
        "content_digest": inventory["whole_source_digest"],
        "selected_items": [],
    }


def _empty_path_entry(inventory: Mapping[str, Any]) -> dict[str, JsonValue]:
    return {
        "source_key": cast(str, inventory["source_key"]),
        "path": None,
        "content_digest": cast(str, inventory["whole_source_digest"]),
        "bytes": 0,
        "rows": 0,
        "device": None,
        "inode": None,
    }


def _semantic_sort_key(item: Mapping[str, JsonValue]) -> tuple[str, str, str]:
    identity = cast(dict[str, JsonValue], item["identity"])
    return (
        str(identity["namespace"]),
        str(identity["immutable_source_id"]),
        str(identity["source_version"]),
    )


def _mismatches(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    semantic_a: bytes,
    semantic_b: bytes,
) -> list[str]:
    keys = (
        "cutover_id",
        "selection_digest",
        "sources",
        "target_inventory",
        "path_manifest_digest",
        "semantic_export_digest",
    )
    mismatches = [key for key in keys if first.get(key) != second.get(key)]
    if semantic_a != semantic_b:
        mismatches.append("semantic_bytes")
    return mismatches
