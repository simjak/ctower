"""Read-only, fail-closed analysis of a frozen Mission Control Request ledger."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from tools.migration.ctower_project.ctower_project_source.canonical import (
    artifact_digest,
    canonical_digest,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

__all__ = ["analyze_cutover"]

_REQUEST_ID = re.compile(r"^R([1-9][0-9]*)$")
_SOURCE_REQUEST_ID = re.compile(r"^R(0*[1-9][0-9]*)$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_OPEN = frozenset({"NEW", "TRIAGED", "WIP", "BLOCKED"})
_TERMINAL = frozenset({"DONE", "SUPERSEDED", "MERGED", "WONT-DO"})
_ALIASES = {
    "ACK": "TRIAGED",
    "ACKNOWLEDGED": "TRIAGED",
    "ACTIVE": "WIP",
    "IN-PROGRESS": "WIP",
    "IN_PROGRESS": "WIP",
    "WORKING": "WIP",
}
_KNOWN_RELATIONSHIPS = frozenset({"refines", "part-of-thread", "merged-into", "superseded-by"})
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_BATCH_SIZE = 25


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
    rows = [item for item in physical if _is_request(item.value)]
    latest, lineage_blockers = _latest_and_lineage(rows)
    mappings, reviews, map_digest, mapping_blockers = _owner_map(owner_map_path)
    blockers = list(lineage_blockers)
    blocker_counts, open_rows, maximum, projections, manifest_rows = _analyze_rows(
        rows, latest, mappings, reviews
    )
    if stat.S_IMODE(source_identity["mode"]) & 0o222:
        blockers.append("source-ledger-writable")
    blockers.extend(_fence_blockers(fence_proof_path, ledger_digest))
    blockers.extend(mapping_blockers)
    for key, count in sorted(blocker_counts.items()):
        blockers.append(f"{key}:{count}")
    counts = _counts(physical, latest, open_rows)
    manifest = _manifest(
        manifest_rows,
        counts,
        ledger_digest=ledger_digest,
        map_digest=map_digest,
        maximum=maximum,
        source_identity=source_identity,
    )
    manifest, manifest_digest = _seal_manifest(manifest, signer, blockers)
    _recheck_source(ledger_path, source_identity, ledger_digest)
    unique_blockers = sorted(set(blockers))
    return {
        "schema": "ctower.request-cutover-dry-run/v1",
        "mode": "DRY-RUN",
        "eligible": not unique_blockers,
        "blockers": unique_blockers,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "batches": _batches(manifest_rows, ledger_digest),
        "counts": counts,
        "ledger_sha256": ledger_digest,
        "manifest": manifest,
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
        "open_by_project": dict(sorted(by_project.items())),
    }


def _manifest(
    rows: list[dict[str, object]],
    counts: Mapping[str, object],
    *,
    ledger_digest: str,
    map_digest: str | None,
    maximum: int,
    source_identity: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "schema": "ctower.request-import-manifest/v1",
        "archive_ref": f"restricted-archive:{ledger_digest.removeprefix('sha256:')}",
        "batch_size": _BATCH_SIZE,
        "counts": dict(counts),
        "ledger_sha256": ledger_digest,
        "maximum_request_number": maximum,
        "open_request_ids": [str(item["id"]) for item in rows],
        "owner_mapping_sha256": map_digest,
        "rows": rows,
        "source_identity": {
            "device": source_identity["device"],
            "inode": source_identity["inode"],
            "size": source_identity["size"],
        },
    }


def _seal_manifest(
    manifest: dict[str, Any], signer: ArtifactSigner | None, blockers: list[str]
) -> tuple[dict[str, Any], str]:
    if signer is not None:
        sealed = signer.seal(manifest, "manifest_digest")
        return sealed, cast(str, sealed["manifest_digest"])
    digest = artifact_digest(manifest, "manifest_digest", "signature")
    manifest["manifest_digest"] = digest
    manifest["signature"] = None
    blockers.append("manifest-unsigned")
    return manifest, digest


class _Line:
    __slots__ = ("digest", "line_number", "value")

    def __init__(self, line_number: int, value: dict[str, object], digest: str) -> None:
        self.line_number = line_number
        self.value = value
        self.digest = digest


def _analyze_rows(
    rows: list[_Line],
    latest: Mapping[str, _Line],
    mappings: Mapping[tuple[str | None, str | None], Mapping[str, str]],
    reviews: Mapping[str, str],
) -> tuple[Counter[str], list[_Line], int, dict[str, object], list[dict[str, object]]]:
    blocker_counts: Counter[str] = Counter()
    maximum = _source_high_water(rows, blocker_counts)
    open_rows: list[_Line] = []
    projections: dict[str, object] = {}
    manifest_rows: list[dict[str, object]] = []
    for request_id, item in sorted(latest.items(), key=lambda pair: _number(pair[0])):
        manifest_row = _analyze_latest(
            request_id, item, mappings, reviews, blocker_counts=blocker_counts
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
        match = _SOURCE_REQUEST_ID.fullmatch(_id(item.value))
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
    )


def _open_row_problems(
    row: Mapping[str, object],
    status: str,
    project: str | None,
    owner: str | None,
    mapping: Mapping[str, str] | None,
    priority: str | None,
) -> list[str]:
    problems: list[str] = []
    if project is None or _PROJECT.fullmatch(project) is None:
        problems.append("open-project-unbound")
    if owner is None:
        problems.append("open-owner-unbound")
    if mapping is None:
        problems.append("owner-map-missing")
    if status != "NEW" and priority is None:
        problems.append("priority-review-missing")
    relation_problem = _relationship_problem(row)
    if relation_problem is not None:
        problems.append(relation_problem)
    if status == "BLOCKED" and not _optional_text(row.get("note")):
        problems.append("blocked-reason-missing")
    return problems


def _read_stable_regular(path: Path) -> tuple[bytes, dict[str, int]]:
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("source-ledger-not-regular")
    if metadata.st_size > _MAX_SOURCE_BYTES:
        raise ValueError("source-ledger-too-large")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("source-ledger-identity-drift")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_SOURCE_BYTES:
                raise ValueError("source-ledger-too-large")
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks), {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "mtime_ns": metadata.st_mtime_ns,
        "size": metadata.st_size,
    }


def _recheck_source(path: Path, identity: Mapping[str, int], digest: str) -> None:
    data, observed = _read_stable_regular(path)
    for key in ("device", "inode", "mode", "mtime_ns", "size"):
        if observed[key] != identity[key]:
            raise ValueError("source-ledger-drift")
    if _sha256(data) != digest:
        raise ValueError("source-ledger-digest-drift")


def _parse_jsonl(data: bytes) -> list[_Line]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("source-ledger-not-utf8") from error
    result: list[_Line] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"source-ledger-malformed-line:{line_number}") from error
        if not isinstance(value, dict):
            raise TypeError(f"source-ledger-nonobject-line:{line_number}")
        result.append(_Line(line_number, cast(dict[str, object], value), _sha256(raw.encode())))
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-json-key")
        value[key] = item
    return value


def _latest_and_lineage(rows: list[_Line]) -> tuple[dict[str, _Line], list[str]]:
    grouped: dict[str, list[_Line]] = defaultdict(list)
    blockers: list[str] = []
    for item in rows:
        request_id = _id(item.value)
        if _SOURCE_REQUEST_ID.fullmatch(request_id) is None:
            blockers.append(f"request-id-invalid:{item.line_number}")
            continue
        if _REQUEST_ID.fullmatch(request_id) is None:
            blockers.append(f"request-id-noncanonical:{request_id}")
        grouped[request_id].append(item)
    for request_id, lineage in grouped.items():
        blockers.extend(_lineage_blockers(request_id, lineage))
    return {request_id: lineage[-1] for request_id, lineage in grouped.items()}, blockers


def _lineage_blockers(request_id: str, lineage: list[_Line]) -> list[str]:
    problems: list[str] = []
    text_values = {_optional_text(item.value.get("text")) for item in lineage}
    created_values = {_optional_text(item.value.get("created")) for item in lineage}
    projects = {
        project
        for item in lineage
        if (project := _optional_text(item.value.get("project"))) is not None
    }
    if len(text_values) != 1 or None in text_values:
        problems.append(f"lineage-text-diverged:{request_id}")
    if len(created_values) != 1 or None in created_values:
        problems.append(f"lineage-created-diverged:{request_id}")
    if len(projects) > 1:
        problems.append(f"lineage-project-diverged:{request_id}")
    problems.extend(_history_blockers(request_id, lineage))
    return problems


def _history_blockers(request_id: str, lineage: list[_Line]) -> list[str]:
    histories = [item.value.get("history") for item in lineage]
    if any(not isinstance(history, list) or not history for history in histories):
        return [f"lineage-history-missing:{request_id}"]
    forked = any(
        cast(list[object], histories[index])
        != cast(list[object], histories[index + 1])[: len(cast(list[object], histories[index]))]
        for index in range(len(histories) - 1)
    )
    return [f"lineage-history-fork:{request_id}"] if forked else []


def _owner_map(
    path: Path | None,
) -> tuple[
    dict[tuple[str | None, str | None], dict[str, str]],
    dict[str, str],
    str | None,
    list[str],
]:
    if path is None:
        return {}, {}, None, ["owner-map-missing"]
    data, _identity = _read_stable_regular(path)
    try:
        value = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError("owner-map-malformed") from error
    if not isinstance(value, dict) or value.get("schema") != "ctower.request-owner-map/v1":
        raise ValueError("owner-map-schema-invalid")
    if not isinstance(value.get("reviewed_by"), str) or not isinstance(
        value.get("reviewed_at"), str
    ):
        raise TypeError("owner-map-review-missing")
    mappings = _owner_mappings(value.get("mappings", []))
    reviews = _request_reviews(value.get("request_reviews", []))
    return mappings, reviews, canonical_digest(cast(dict[str, Any], value)), []


def _owner_mappings(
    entries: object,
) -> dict[tuple[str | None, str | None], dict[str, str]]:
    mappings: dict[tuple[str | None, str | None], dict[str, str]] = {}
    for item in cast(list[object], entries):
        if not isinstance(item, dict):
            raise TypeError("owner-map-entry-invalid")
        project = item.get("project_key")
        owner = item.get("source_owner")
        principal = item.get("principal_id")
        if not all(isinstance(member, str) and member for member in (project, owner, principal)):
            raise ValueError("owner-map-entry-invalid")
        key = (cast(str, project), cast(str, owner))
        if key in mappings:
            raise ValueError("owner-map-entry-duplicate")
        mappings[key] = {
            "principal_id": cast(str, principal),
            "project_key": cast(str, project),
            "source_owner": cast(str, owner),
        }
    return mappings


def _request_reviews(entries: object) -> dict[str, str]:
    reviews: dict[str, str] = {}
    for item in cast(list[object], entries):
        if not isinstance(item, dict):
            raise TypeError("request-review-invalid")
        request_id, priority = item.get("id"), item.get("priority")
        if not isinstance(request_id, str) or priority not in {"P0", "P1", "P2"}:
            raise ValueError("request-review-invalid")
        if request_id in reviews:
            raise ValueError("request-review-duplicate")
        reviews[request_id] = cast(str, priority)
    return reviews


def _fence_blockers(path: Path | None, ledger_digest: str) -> list[str]:
    if path is None:
        return ["source-fence-proof-missing"]
    data, _identity = _read_stable_regular(path)
    try:
        value = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError("source-fence-proof-malformed") from error
    if not isinstance(value, dict) or value.get("schema") != "ctower.request-source-fence/v1":
        return ["source-fence-proof-invalid"]
    blockers: list[str] = []
    if value.get("ledger_sha256") != ledger_digest:
        blockers.append("fence-ledger-digest-unbound")
    if value.get("writer_refuses") is not True:
        blockers.append("source-writer-not-refusing")
    if value.get("mutation_entrypoints_removed") is not True:
        blockers.append("source-mutation-entrypoints-present")
    return blockers


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
) -> dict[str, object]:
    row = item.value
    text = _optional_text(row.get("text")) or ""
    owner_digest = _sha256((owner or "").encode())
    refines = row.get("refines") or []
    if not isinstance(refines, list):
        raise TypeError("request-refines-invalid")
    return {
        "content_sha256": _sha256(text.encode()),
        "created": _optional_text(row.get("created")),
        "id": request_id,
        "latest_line": item.line_number,
        "latest_row_sha256": item.digest,
        "mapped_principal_id": None if mapping is None else mapping["principal_id"],
        "original_owner_sha256": owner_digest,
        "priority": priority,
        "project_key": project,
        "projection": dict(projection),
        "refines": list(refines),
        "relationships_sha256": canonical_digest(
            cast(dict[str, Any], {"relationships": row.get("relationships") or []})
        ),
        "source_owner": owner,
        "source_status": status,
        "updated": _optional_text(row.get("updated")),
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
                "sample": [
                    {
                        "content_sha256": item["content_sha256"],
                        "id": item["id"],
                        "latest_row_sha256": item["latest_row_sha256"],
                        "project_key": item["project_key"],
                    }
                    for item in sample
                ],
                "sample_count": len(sample),
                "source_count": len(batch),
                "source_count_by_project": dict(
                    sorted(Counter(str(item["project_key"]) for item in batch).items())
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


def _historical_values(value: object) -> Iterable[str | None]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {"id", "owner", "project", "created", "updated"}:
                yield from _historical_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _historical_values(item)


def _is_request(value: Mapping[str, object]) -> bool:
    return str(value.get("record_type") or "request").strip().lower() == "request" and _id(
        value
    ).startswith("R")


def _id(value: Mapping[str, object]) -> str:
    return str(value.get("id") or "").strip().upper()


def _status(value: object) -> str:
    status = str(value or "NEW").strip().upper()
    return _ALIASES.get(status, status)


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(request_id: str) -> int:
    match = _SOURCE_REQUEST_ID.fullmatch(request_id)
    return int(match.group(1)) if match is not None else 2**63 - 1


def _count(counter: Counter[str], key: str) -> None:
    counter[key] += 1


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
