"""Read-only, fail-closed analysis of a frozen Mission Control Request ledger."""

from __future__ import annotations

import hashlib
import re
import stat
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

from ctower_contracts import validator_for

from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from tools.migration.ctower_project.ctower_project_source.canonical import canonical_digest
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests._dry_run_evidence import (
    fence_proof as _fence_proof,
)
from tools.migration.operator_requests._dry_run_evidence import (
    owner_map as _owner_map,
)
from tools.migration.operator_requests._dry_run_lineage import (
    latest_and_lineage as _latest_and_lineage,
)
from tools.migration.operator_requests._dry_run_source import (
    SourceLine as _Line,
)
from tools.migration.operator_requests._dry_run_source import (
    classification_blockers as _classification_blockers,
)
from tools.migration.operator_requests._dry_run_source import (
    historical_values as _historical_values,
)
from tools.migration.operator_requests._dry_run_source import (
    is_request as _is_request,
)
from tools.migration.operator_requests._dry_run_source import (
    optional_text as _optional_text,
)
from tools.migration.operator_requests._dry_run_source import (
    parse_jsonl as _parse_jsonl,
)
from tools.migration.operator_requests._dry_run_source import (
    read_stable_regular as _read_stable_regular,
)
from tools.migration.operator_requests._dry_run_source import (
    recheck_source as _recheck_source,
)
from tools.migration.operator_requests._dry_run_source import (
    request_id as _id,
)
from tools.migration.operator_requests._dry_run_source import (
    request_number as _number,
)
from tools.migration.operator_requests._dry_run_source import (
    sha256 as _sha256,
)
from tools.migration.operator_requests._dry_run_source import (
    source_timestamp as _source_timestamp,
)
from tools.migration.operator_requests._dry_run_source import (
    status as _status,
)

__all__ = ["analyze_cutover"]

_SOURCE_REQUEST_ID = re.compile(r"^R(0*[1-9][0-9]*)$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_OPEN = frozenset({"NEW", "TRIAGED", "WIP", "BLOCKED"})
_TERMINAL = frozenset({"DONE", "SUPERSEDED", "MERGED", "WONT-DO"})
_KNOWN_RELATIONSHIPS = frozenset({"refines", "part-of-thread", "merged-into", "superseded-by"})
_BATCH_SIZE = 25
_CUTOVER_NAMESPACE = UUID("4a4fa05a-15ee-55d5-942b-6427217ab3bf")


def analyze_cutover(
    ledger_path: Path,
    *,
    owner_map_path: Path | None = None,
    fence_proof_path: Path | None = None,
    signer: ArtifactSigner | None = None,
    shadow_observation: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Derive the denominator once without writing source, target, or archive state."""

    source_bytes, source_identity = _read_stable_regular(ledger_path)
    ledger_digest = _sha256(source_bytes)
    physical = _parse_jsonl(source_bytes)
    classification_blockers = _classification_blockers(physical)
    rows = [item for item in physical if _is_request(item.value)]
    latest, lineage_blockers = _latest_and_lineage(rows)
    (
        mappings,
        reviews,
        map_digest,
        target_tenant_id,
        target_authority_digest,
        mapping_blockers,
    ) = _owner_map(owner_map_path)
    blockers = [*classification_blockers, *lineage_blockers]
    blocker_counts, open_rows, maximum, projections, manifest_rows = _analyze_rows(
        physical, latest, mappings, reviews, ledger_digest=ledger_digest
    )
    if stat.S_IMODE(cast(int, source_identity["mode"])) & 0o222:
        blockers.append("source-ledger-writable")
    fence, fence_blockers = _fence_proof(
        fence_proof_path,
        ledger_digest,
        source_identity=source_identity,
        signer=signer,
    )
    blockers.extend(fence_blockers)
    blockers.extend(mapping_blockers)
    blockers.extend(f"{key}:{count}" for key, count in sorted(blocker_counts.items()))
    counts = _counts(physical, latest, open_rows)
    manifest = _manifest(
        manifest_rows,
        counts,
        ledger_digest=ledger_digest,
        map_digest=map_digest,
        maximum=maximum,
        source_identity=source_identity,
        fence_digest=None if fence is None else cast(str, fence["fence_digest"]),
        target_authority_digest=target_authority_digest,
        target_tenant_id=target_tenant_id,
    )
    manifest_artifact, manifest_digest = _seal_manifest(manifest, signer, blockers)
    _recheck_source(ledger_path, source_identity, ledger_digest)
    return _analysis_result(
        blockers=blockers,
        blocker_counts=blocker_counts,
        counts=counts,
        ledger_digest=ledger_digest,
        manifest=manifest,
        manifest_artifact=manifest_artifact,
        manifest_digest=manifest_digest,
        maximum=maximum,
        projections=projections,
        shadow_observation=shadow_observation,
    )


def _analysis_result(
    *,
    blockers: list[str],
    blocker_counts: Counter[str],
    counts: dict[str, object],
    ledger_digest: str,
    manifest: dict[str, Any],
    manifest_artifact: dict[str, Any] | None,
    manifest_digest: str | None,
    maximum: int,
    projections: dict[str, object],
    shadow_observation: Mapping[str, object] | None,
) -> dict[str, Any]:
    unique_blockers = sorted(set(blockers))
    return {
        "schema": "ctower.request-cutover-dry-run/v1",
        "mode": "DRY-RUN",
        "eligible": not unique_blockers,
        "blockers": unique_blockers,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "batches": manifest["batches"],
        "counts": counts,
        "ledger_sha256": ledger_digest,
        "diagnostic_manifest": manifest,
        "manifest": manifest_artifact,
        "manifest_digest": manifest_digest,
        "maximum_request_number": maximum,
        "projections": projections,
        "shadow": dict(shadow_observation or {}),
        "writes_attempted": 0,
    }


def _counts(
    physical: list[_Line], latest: Mapping[str, _Line], open_rows: list[_Line]
) -> dict[str, object]:
    by_project = Counter(
        cast(str, item.value["project"])
        for item in open_rows
        if isinstance(item.value.get("project"), str)
    )
    return {
        "physical_rows": len(physical),
        "logical_requests": len(latest),
        "open_requests": len(open_rows),
        "open_by_project": _project_count_items(by_project),
    }


def _project_count_items(counts: Mapping[str, int]) -> list[dict[str, object]]:
    return [
        {"project_key": project_key, "count": count}
        for project_key, count in sorted(counts.items())
    ]


def _manifest(
    rows: list[dict[str, object]],
    counts: Mapping[str, object],
    *,
    ledger_digest: str,
    map_digest: str | None,
    maximum: int,
    source_identity: Mapping[str, object],
    fence_digest: str | None,
    target_authority_digest: str | None,
    target_tenant_id: str | None,
) -> dict[str, Any]:
    rows_digest = canonical_digest(cast(list[Any], rows))
    batches = _batches(rows, rows_digest)
    return {
        "schema": "ctower.request-import-manifest/v1",
        "archive_ref": f"restricted-archive:{ledger_digest.removeprefix('sha256:')}",
        "batch_size": _BATCH_SIZE,
        "counts": dict(counts),
        "fence_digest": fence_digest,
        "ledger_sha256": ledger_digest,
        "maximum_request_number": maximum,
        "open_request_ids": [str(item["id"]) for item in rows],
        "owner_mapping_sha256": map_digest,
        "rows_digest": rows_digest,
        "rows": rows,
        "sampling_seed": rows_digest,
        "batches": batches,
        "source_identity": {
            "device": source_identity["device"],
            "inode": source_identity["inode"],
            "size": source_identity["size"],
            "mode": source_identity["mode"],
            "mtime_ns": source_identity["mtime_ns"],
        },
        "target_authority_digest": target_authority_digest,
        "target_tenant_id": target_tenant_id,
    }


def _seal_manifest(
    manifest: dict[str, Any], signer: ArtifactSigner | None, blockers: list[str]
) -> tuple[dict[str, Any] | None, str | None]:
    if signer is not None and not blockers:
        sealed = signer.seal(manifest, "manifest_digest")
        validator_for("ctower.request-import-manifest/v1").validate(sealed)
        return sealed, cast(str, sealed["manifest_digest"])
    if signer is None:
        blockers.append("manifest-unsigned")
    return None, None


def _analyze_rows(
    physical: list[_Line],
    latest: Mapping[str, _Line],
    mappings: Mapping[tuple[str | None, str | None], Mapping[str, str]],
    reviews: Mapping[str, str],
    *,
    ledger_digest: str,
) -> tuple[Counter[str], list[_Line], int, dict[str, object], list[dict[str, object]]]:
    blocker_counts: Counter[str] = Counter()
    maximum = _source_high_water(physical, blocker_counts)
    open_rows: list[_Line] = []
    projections: dict[str, object] = {}
    manifest_rows: list[dict[str, object]] = []
    for request_id, item in sorted(latest.items(), key=lambda pair: _number(pair[0])):
        manifest_row = _analyze_latest(
            request_id,
            item,
            mappings,
            reviews,
            ledger_digest=ledger_digest,
            blocker_counts=blocker_counts,
        )
        if manifest_row is None:
            continue
        open_rows.append(item)
        projections[request_id] = cast(dict[str, object], manifest_row["projection"])
        manifest_rows.append(manifest_row)
    return blocker_counts, open_rows, maximum, projections, manifest_rows


def _source_high_water(rows: list[_Line], blocker_counts: Counter[str]) -> int:
    maximum = 0
    for item in rows:
        match = _SOURCE_REQUEST_ID.fullmatch(_id(item.value)) if _is_request(item.value) else None
        if match is not None:
            maximum = max(maximum, int(match.group(1)))
        prohibited = prohibited_data_refusal(_historical_values(item.value))
        if prohibited is not None:
            for item_class in prohibited.prohibited_classes:
                _count(blocker_counts, f"prohibited-history:{item_class}")
    return maximum


def _analyze_latest(
    request_id: str,
    item: _Line,
    mappings: Mapping[tuple[str | None, str | None], Mapping[str, str]],
    reviews: Mapping[str, str],
    *,
    ledger_digest: str,
    blocker_counts: Counter[str],
) -> dict[str, object] | None:
    row = item.value
    status = _status(row.get("status"))
    if status not in _OPEN | _TERMINAL:
        _count(blocker_counts, "status-unknown")
        return None
    if status in _TERMINAL:
        return None
    project = _optional_text(row.get("project"))
    owner = _optional_text(row.get("owner"))
    mapping = mappings.get((project, owner))
    priority = reviews.get(request_id)
    for problem in _open_row_problems(row, status, project, owner, mapping, priority):
        _count(blocker_counts, problem)
    return _manifest_row(
        request_id,
        item,
        status=status,
        project=project,
        owner=owner,
        mapping=mapping,
        priority=priority,
        projection=_projection(status, priority),
        ledger_digest=ledger_digest,
    )


def _open_row_problems(
    row: Mapping[str, object],
    status: str,
    project: str | None,
    owner: str | None,
    mapping: Mapping[str, str] | None,
    priority: str | None,
) -> list[str]:
    problems = _binding_problems(project, owner, mapping)
    problems.extend(_review_problems(status, priority))
    relation_problem = _relationship_problem(row)
    if relation_problem is not None:
        problems.append(relation_problem)
    if status == "BLOCKED" and not _optional_text(row.get("note")):
        problems.append("blocked-reason-missing")
    if not _valid_row_timestamps(row):
        problems.append("source-timestamp-invalid")
    return problems


def _binding_problems(
    project: str | None,
    owner: str | None,
    mapping: Mapping[str, str] | None,
) -> list[str]:
    problems: list[str] = []
    if project is None or _PROJECT.fullmatch(project) is None:
        problems.append("open-project-unbound")
    if owner is None:
        problems.append("open-owner-unbound")
    if mapping is None:
        problems.append("owner-map-missing")
    return problems


def _review_problems(status: str, priority: str | None) -> list[str]:
    if status != "NEW" and priority is None:
        return ["priority-review-missing"]
    return []


def _valid_row_timestamps(row: Mapping[str, object]) -> bool:
    return not (
        _source_timestamp(row.get("created")) is None
        or _source_timestamp(row.get("updated")) is None
    )


def _projection(status: str, priority: str | None) -> dict[str, object]:
    if status == "NEW":
        return {"blocker": False, "priority": "P2", "state": "NEW", "triage": "UNTRIAGED"}
    return {
        "blocker": status == "BLOCKED",
        "priority": priority,
        "state": "TRIAGED",
        "triage": "ACCEPTED",
    }


def _manifest_row(
    request_id: str,
    item: _Line,
    *,
    status: str,
    project: str | None,
    owner: str | None,
    mapping: Mapping[str, str] | None,
    priority: str | None,
    projection: Mapping[str, object],
    ledger_digest: str,
) -> dict[str, object]:
    del priority
    row = item.value
    text = _optional_text(row.get("text")) or ""
    owner_digest = _sha256((owner or "").encode())
    refines = row.get("refines") or []
    if not isinstance(refines, list):
        raise TypeError("request-refines-invalid")
    source_number = _number(request_id)
    return {
        "command_id": str(
            uuid5(
                _CUTOVER_NAMESPACE,
                f"{ledger_digest}:{request_id}:import:1",
            )
        ),
        "content_sha256": _sha256(text.encode()),
        "created_at": _source_timestamp(row.get("created")),
        "id": request_id,
        "latest_line": item.line_number,
        "latest_row_sha256": item.digest,
        "mapped_principal_id": None if mapping is None else mapping["principal_id"],
        "original_owner_sha256": owner_digest,
        "priority": projection["priority"],
        "project_key": project,
        "projection": dict(projection),
        "refines": list(refines),
        "relationships_sha256": canonical_digest(
            cast(dict[str, Any], {"relationships": row.get("relationships") or []})
        ),
        "request_id": str(
            uuid5(
                _CUTOVER_NAMESPACE,
                f"{ledger_digest}:{request_id}:request",
            )
        ),
        "request_number": source_number,
        "source_owner": owner,
        "source_status": status,
        "updated_at": _source_timestamp(row.get("updated")),
    }


def _batches(rows: list[dict[str, object]], seed_digest: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for batch_index, start in enumerate(range(0, len(rows), _BATCH_SIZE)):
        batch = rows[start : start + _BATCH_SIZE]
        ranked = sorted(
            batch,
            key=lambda item: hashlib.sha256(
                f"{seed_digest}:{batch_index}:{item['id']}".encode()
            ).digest(),
        )
        sample = sorted(ranked[: min(3, len(ranked))], key=lambda item: str(item["id"]))
        result.append(
            {
                "batch_index": batch_index,
                "batch_digest": canonical_digest(cast(list[Any], batch)),
                "cumulative_count": start + len(batch),
                "sample_ids": [str(item["id"]) for item in sample],
                "source_count": len(batch),
                "source_count_by_project": _project_count_items(
                    Counter(str(item["project_key"]) for item in batch)
                ),
            }
        )
    return result


def _relationship_problem(row: Mapping[str, object]) -> str | None:
    relationships = row.get("relationships") or []
    if not isinstance(relationships, list):
        return "relationship-shape-invalid"
    kinds, problem = _relationship_kinds(relationships)
    if problem is not None:
        return problem
    if _status(row.get("status")) in _OPEN and kinds & {"merged-into", "superseded-by"}:
        return "open-terminal-relationship"
    return _refines_problem(row.get("refines") or [])


def _relationship_kinds(relationships: list[object]) -> tuple[set[str], str | None]:
    kinds: set[str] = set()
    for item in relationships:
        if not isinstance(item, dict):
            return kinds, "relationship-shape-invalid"
        kind = item.get("kind") or item.get("type")
        if not isinstance(kind, str) or kind not in _KNOWN_RELATIONSHIPS:
            return kinds, "relationship-kind-unknown"
        kinds.add(kind)
    return kinds, None


def _refines_problem(refines: object) -> str | None:
    if not isinstance(refines, list) or any(not isinstance(item, str) for item in refines):
        return "refines-shape-invalid"
    return None


def _count(counter: Counter[str], key: str) -> None:
    counter[key] += 1
