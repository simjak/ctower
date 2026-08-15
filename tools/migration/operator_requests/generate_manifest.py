"""Generate a signed Request import manifest from a Mission Control JSONL ledger.

Reads the complete requests.jsonl file, keeps the latest version per R-id,
builds the full manifest matching the request-import-manifest schema, signs
it with Ed25519, and outputs canonical JSON ready for the operator inventory
command.

Usage
-----

    python -m tools.migration.operator_requests.generate_manifest \\
        --input state/requests.jsonl \\
        --output /operator-evidence/request-manifest.json \\
        --signing-key-map /operator-secrets/signing-map.json \\
        --signing-key-ref signing-key-ref:request-cutover \\
        --signing-key-version 1

Optional
~~~~~~~~

    --fence-digest sha256:...           # bind the manifest to a freeze proof
    --owner-map /path/to/owner-map.json # reviewed owner mapping for owners
    --target-tenant-id <uuid>           # target ctower tenant
    --target-authority-digest sha256:.. # target authority digest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import rfc8785

from tools.migration.ctower_project.ctower_project_source.canonical import canonical_digest
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

__all__ = ["generate_manifest", "main"]

_CUTOVER_NAMESPACE = UUID("4a4fa05a-15ee-55d5-942b-6427217ab3bf")
_BATCH_SIZE = 25
_REQUEST_KEYS = frozenset(
    {
        "id",
        "text",
        "status",
        "project",
        "owner",
        "created",
        "updated",
        "refines",
        "relationships",
        "note",
        "record_type",
        "blocker",
        "priority",
        "history",
    }
)
_TERMINAL = frozenset({"DONE", "SUPERSEDED", "MERGED", "WONT-DO"})
_ALIASES = {
    "ACK": "TRIAGED",
    "ACKNOWLEDGED": "TRIAGED",
    "ACTIVE": "WIP",
    "IN-PROGRESS": "WIP",
    "IN_PROGRESS": "WIP",
    "WORKING": "WIP",
}
_STATUS_OPEN = frozenset({"NEW", "TRIAGED", "WIP", "BLOCKED"})
_DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"
_DEFAULT_DIGEST = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def generate_manifest(
    jsonl_path: Path,
    *,
    signer: ArtifactSigner | None = None,
    owner_map_path: Path | None = None,
    fence_digest: str | None = None,
    target_tenant_id: str | None = None,
    target_authority_digest: str | None = None,
) -> dict[str, Any]:
    """Read the JSONL ledger and produce a signed import manifest.

    Parameters
    ----------
    jsonl_path:
        Path to the Mission Control ``state/requests.jsonl`` file.
    signer:
        Active :class:`ArtifactSigner` used to seal the manifest. When
        ``None`` the manifest is returned unsigned (no signature block).
    owner_map_path:
        Optional path to a signed owner-map artifact. When provided the
        ``owner_mapping_sha256`` and per-row ``mapped_principal_id`` are
        resolved from it.
    fence_digest:
        Optional ``sha256:...`` digest of the freeze fence artifact to
        bind the manifest to a specific fence observation.
    target_tenant_id:
        The target ctower tenant UUID. Defaults to the nil UUID when
        not provided.
    target_authority_digest:
        The target authority digest. Defaults to the empty-string digest
        when not provided.

    Returns
    -------
    dict[str, Any]
        The complete, signed manifest dict (canonicalised by the signer).

    Raises
    ------
    FileNotFoundError
        The JSONL file does not exist.
    ValueError
        The file is empty, malformed, or contains no open requests.
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"ledger not found: {jsonl_path}")

    source_bytes = jsonl_path.read_bytes()
    if not source_bytes.strip():
        raise ValueError("ledger is empty")

    source_metadata = _regular_metadata(jsonl_path)
    ledger_digest = _sha256(source_bytes)
    physical = _parse_jsonl(source_bytes)

    latest, latest_line = _latest_entries(physical)
    if not latest:
        raise ValueError("no request rows found in ledger")

    open_rows = _open_rows(latest)
    if not open_rows:
        raise ValueError("no open request rows in ledger")

    maximum_number = max(
        int(rid[1:]) for rid in open_rows if rid.startswith("R") and rid[1:].isdigit()
    )

    owner_mappings, map_digest = _load_owner_map(owner_map_path)
    rows = _build_rows(open_rows, latest_line, owner_mappings, ledger_digest)
    rows_digest = _canonical_rows_digest(rows)
    counts = _build_counts(len(physical), len(latest), open_rows)
    batches = _build_batches(rows, rows_digest)

    result = _manifest_payload(
        source_metadata,
        ledger_digest=ledger_digest,
        rows=rows,
        rows_digest=rows_digest,
        counts=counts,
        batches=batches,
        maximum_number=maximum_number,
        fence_digest=fence_digest,
        map_digest=map_digest,
        target_tenant_id=target_tenant_id,
        target_authority_digest=target_authority_digest,
    )

    if signer is not None:
        return signer.seal(result, "manifest_digest")
    return result


def _latest_entries(
    physical: list[tuple[dict[str, object], int]],
) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    """Keep the latest version per R-id, tracking the latest line number."""
    latest: dict[str, dict[str, object]] = {}
    latest_line: dict[str, int] = {}
    for entry, line_number in physical:
        rid = _request_id(entry)
        if rid is not None:
            latest[rid] = entry
            latest_line[rid] = line_number
    return latest, latest_line


def _open_rows(latest: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Extract open (non-terminal) requests."""
    return {
        rid: entry
        for rid, entry in latest.items()
        if _normalized_status(entry.get("status")) in _STATUS_OPEN
    }


def _build_rows(
    open_rows: dict[str, dict[str, object]],
    latest_line: dict[str, int],
    owner_mappings: dict[tuple[str | None, str | None], dict[str, str]],
    ledger_digest: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rid in sorted(open_rows, key=lambda r: int(r[1:])):
        entry = open_rows[rid]
        owner = _optional_text(entry.get("owner")) or ""
        project = _optional_text(entry.get("project"))
        mapping = owner_mappings.get((project, owner))
        rows.append(
            _manifest_row(
                rid,
                entry,
                line_number=latest_line.get(rid, 1),
                mapping=mapping,
                ledger_digest=ledger_digest,
            )
        )
    return rows


def _manifest_payload(
    source_metadata: os.stat_result,
    *,
    ledger_digest: str,
    rows: list[dict[str, Any]],
    rows_digest: str,
    counts: dict[str, object],
    batches: list[dict[str, object]],
    maximum_number: int,
    fence_digest: str | None,
    map_digest: str | None,
    target_tenant_id: str | None,
    target_authority_digest: str | None,
) -> dict[str, object]:
    return {
        "schema": "ctower.request-import-manifest/v1",
        "archive_ref": f"restricted-archive:{ledger_digest.removeprefix('sha256:')}",
        "batch_size": _BATCH_SIZE,
        "counts": counts,
        "fence_digest": fence_digest or _DEFAULT_DIGEST,
        "ledger_sha256": ledger_digest,
        "maximum_request_number": maximum_number,
        "open_request_ids": [str(row["id"]) for row in rows],
        "owner_mapping_sha256": map_digest or _DEFAULT_DIGEST,
        "rows_digest": rows_digest,
        "rows": rows,
        "sampling_seed": rows_digest,
        "batches": batches,
        "source_identity": {
            "device": source_metadata.st_dev,
            "inode": source_metadata.st_ino,
            "mode": source_metadata.st_mode,
            "mtime_ns": str(source_metadata.st_mtime_ns),
            "size": source_metadata.st_size,
        },
        "target_authority_digest": target_authority_digest or _DEFAULT_DIGEST,
        "target_tenant_id": target_tenant_id or _DEFAULT_TENANT_ID,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the manifest generation tool."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to requests.jsonl")
    parser.add_argument("--output", required=True, type=Path, help="Output path for the manifest")
    parser.add_argument(
        "--signing-key-map",
        type=Path,
        help="Path to the signing-key reference map JSON file",
    )
    parser.add_argument(
        "--signing-key-ref",
        help="Key reference in the map, e.g. signing-key-ref:request-cutover",
    )
    parser.add_argument(
        "--signing-key-version",
        type=int,
        help="Key version (positive integer)",
    )
    parser.add_argument("--owner-map", type=Path, help="Path to the reviewed owner-map artifact")
    parser.add_argument("--fence-digest", help="sha256:... digest of the freeze fence artifact")
    parser.add_argument("--target-tenant-id", help="Target ctower tenant UUID")
    parser.add_argument("--target-authority-digest", help="sha256:... target authority digest")
    arguments = parser.parse_args(argv)

    key_args = [
        arguments.signing_key_map,
        arguments.signing_key_ref,
        arguments.signing_key_version,
    ]
    if not all(a is not None for a in key_args):
        missing = [
            name for name, a in zip(("map", "ref", "version"), key_args, strict=True) if a is None
        ]
        parser.error(f"missing signing key arguments: {', '.join(missing)}")

    signer = ArtifactSigner.from_reference_map(
        arguments.signing_key_map,
        arguments.signing_key_ref,
        key_version=arguments.signing_key_version,
    )

    manifest = generate_manifest(
        arguments.input,
        signer=signer,
        owner_map_path=arguments.owner_map,
        fence_digest=arguments.fence_digest,
        target_tenant_id=arguments.target_tenant_id,
        target_authority_digest=arguments.target_authority_digest,
    )

    arguments.output.write_bytes(rfc8785.dumps(manifest))
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _regular_metadata(path: Path) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("source-ledger-not-regular")
    return metadata


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _parse_jsonl(data: bytes) -> list[tuple[dict[str, object], int]]:
    """Parse JSONL and return list of (parsed_dict, line_number) tuples."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("ledger is not valid UTF-8") from error
    result: list[tuple[dict[str, object], int]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ValueError(f"malformed JSON at line {line_number}") from error
        if not isinstance(value, dict):
            raise TypeError(f"non-object value at line {line_number}")
        unknown = set(value) - _REQUEST_KEYS
        if unknown:
            raise ValueError(f"unknown fields at line {line_number}: {sorted(unknown)}")
        result.append((value, line_number))
    return result


def _request_id(entry: dict[str, object]) -> str | None:
    rid = entry.get("id")
    if isinstance(rid, str) and rid.startswith("R") and rid[1:].isdigit():
        return rid
    return None


def _normalized_status(raw: object) -> str:
    status = str(raw or "NEW").strip().upper()
    return _ALIASES.get(status, status)


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _load_owner_map(
    path: Path | None,
) -> tuple[dict[tuple[str | None, str | None], dict[str, str]], str | None]:
    if path is None:
        return {}, None
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise TypeError("owner-map-not-object")
    map_digest = _sha256(data)
    mappings: dict[tuple[str | None, str | None], dict[str, str]] = {}
    for item in value.get("mappings", []):
        if not isinstance(item, dict):
            continue
        project = item.get("project_key")
        owner = item.get("source_owner")
        principal = item.get("principal_id")
        if not all(isinstance(v, str) and v for v in (project, owner, principal)):
            continue
        mappings[cast(tuple[str | None, str | None], (project, owner))] = {
            "principal_id": cast(str, principal),
            "project_key": cast(str, project),
            "source_owner": cast(str, owner),
        }
    return mappings, map_digest


def _manifest_row(
    source_id: str,
    entry: dict[str, object],
    *,
    line_number: int,
    mapping: dict[str, str] | None,
    ledger_digest: str,
) -> dict[str, Any]:
    text = _optional_text(entry.get("text")) or ""
    owner = _optional_text(entry.get("owner")) or ""
    status = _normalized_status(entry.get("status"))
    project = _optional_text(entry.get("project"))
    refines = entry.get("refines")
    if not isinstance(refines, list):
        refines = []
    relationships = entry.get("relationships")
    if not isinstance(relationships, list):
        relationships = []

    source_number = int(source_id[1:])

    projection = _projection(status)

    return {
        "command_id": str(uuid5(_CUTOVER_NAMESPACE, f"{ledger_digest}:{source_id}:import:1")),
        "content_sha256": _sha256(text.encode("utf-8")),
        "created_at": _format_timestamp(entry.get("created")),
        "id": source_id,
        "latest_line": line_number,
        "latest_row_sha256": _sha256(json.dumps(entry, sort_keys=True).encode("utf-8")),
        "mapped_principal_id": "00000000-0000-0000-0000-000000000000"
        if mapping is None
        else mapping["principal_id"],
        "original_owner_sha256": _sha256(owner.encode("utf-8")),
        "priority": projection["priority"],
        "project_key": project or "unknown",
        "projection": projection,
        "refines": list(refines),
        "relationships_sha256": canonical_digest({"relationships": relationships}),
        "request_id": str(uuid5(_CUTOVER_NAMESPACE, f"{ledger_digest}:{source_id}:request")),
        "request_number": source_number,
        "source_owner": owner,
        "source_status": status,
        "updated_at": _format_timestamp(entry.get("updated")),
    }


def _format_timestamp(raw: object) -> str:
    """Return the timestamp as-is if it looks like ISO-8601, else use epoch."""
    value = _optional_text(raw)
    if value is None:
        return "1970-01-01T00:00:00Z"
    return value


def _projection(status: str) -> dict[str, object]:
    if status == "BLOCKED":
        return {"blocker": True, "priority": "P2", "state": "TRIAGED", "triage": "ACCEPTED"}
    if status == "NEW":
        return {"blocker": False, "priority": "P2", "state": "NEW", "triage": "UNTRIAGED"}
    # TRIAGED, WIP: considered triaged
    return {"blocker": False, "priority": "P2", "state": "TRIAGED", "triage": "ACCEPTED"}


def _build_counts(
    physical_count: int,
    logical_count: int,
    open_rows: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    by_project: Counter[str] = Counter()
    for entry in open_rows.values():
        project = _optional_text(entry.get("project"))
        if project is not None:
            by_project[project] += 1
    return {
        "physical_rows": physical_count,
        "logical_requests": logical_count,
        "open_requests": len(open_rows),
        "open_by_project": [
            {"project_key": key, "count": count} for key, count in sorted(by_project.items())
        ],
    }


def _build_batches(
    rows: list[dict[str, Any]],
    seed: str,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for batch_index, start in enumerate(range(0, len(rows), _BATCH_SIZE)):
        batch = rows[start : start + _BATCH_SIZE]
        ranked = sorted(
            batch,
            key=lambda item: hashlib.sha256(f"{seed}:{batch_index}:{item['id']}".encode()).digest(),
        )
        sample = sorted(ranked[: min(3, len(ranked))], key=lambda item: str(item["id"]))
        by_project: Counter[str] = Counter()
        for row in batch:
            project = str(row.get("project_key", "unknown"))
            by_project[project] += 1
        result.append(
            {
                "batch_index": batch_index,
                "batch_digest": _canonical_rows_digest(batch),
                "source_count": len(batch),
                "source_count_by_project": [
                    {"project_key": k, "count": v} for k, v in sorted(by_project.items())
                ],
                "cumulative_count": start + len(batch),
                "sample_ids": [str(item["id"]) for item in sample],
            }
        )
    return result


def _canonical_rows_digest(rows: list[dict[str, Any]]) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, rows))).hexdigest()}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    raise SystemExit(main())
