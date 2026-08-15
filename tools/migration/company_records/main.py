"""Operator-authority import planning for Mission Control escape records."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import (
    SeatDisposition,
    build_estate_manifest,
    load_seat_mapping,
    read_stable_source,
)

__all__ = ["analyze_escapes_import", "execute_escapes_import"]

_ESCAPE_NAMESPACE = UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")
_TIER = "company_records"
_SOURCE_PATH = "state/escapes.jsonl"


def _parse_escapes(path: Path) -> list[dict[str, Any]]:
    """Parse strict JSONL, retaining source order and a deterministic record identity."""

    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, dict):
            raise TypeError(f"escape row {line_number} is not an object")
        source_ref = f"{_SOURCE_PATH}#{line_number}"
        canonical = rfc8785.dumps(cast(Any, value))
        record = dict(value)
        record["record_id"] = str(uuid5(_ESCAPE_NAMESPACE, source_ref))
        record["source_ref"] = source_ref
        record["content_sha256"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        records.append(record)
    return records


def analyze_escapes_import(
    escapes_path: Path,
    *,
    project_key: str = "ctower",
    seat_map_path: Path | None = None,
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Build a signed, source-bound estate manifest without mutating ctower."""

    if not escapes_path.is_file():
        return _ineligible(f"file not found: {escapes_path}", project_key)
    _source_bytes, source_identity = read_stable_source(escapes_path)
    records = _parse_escapes(escapes_path)
    dispositions = _load_dispositions(seat_map_path)
    rows = [_manifest_row(record, dispositions) for record in records]
    if not rows:
        return _ineligible("source is empty", project_key, escapes_count=0)
    manifest = build_estate_manifest(
        tier=_TIER,
        source_identity={**source_identity, "source_path": _SOURCE_PATH},
        rows=rows,
        seat_mapping_digest=_mapping_digest(seat_map_path),
        signer=signer,
    )
    unknown = sorted(
        {str(row["source_seat"]) for row in rows if row["_disposition"] == "source_only"}
    )
    return {
        "schema": "ctower.company-records-import-dry-run/v1",
        "mode": "SIGNED" if signer is not None else "DRY-RUN",
        "eligible": True,
        "escapes_count": len(records),
        "project_key": project_key,
        "row_count": len(records),
        "unknown_owner_count": len(unknown),
        "unknown_owners": unknown,
        "writes_attempted": 0,
        "source_digest": source_identity["source_sha256"],
        "manifest": manifest,
    }


def execute_escapes_import(
    client: httpx.Client,
    *,
    escapes_path: Path,
    manifest: dict[str, Any],
    base_url: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    """Send one signed company-record batch through the operator-only API seam."""

    records = _parse_escapes(escapes_path)
    rows = [_request_row(record) for record in records]
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    response = client.post(
        f"{base_url}/v1/migrations/estate/company-records",
        json={"manifest": manifest, "rows": rows},
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    (evidence_dir / "parity.json").write_bytes(rfc8785.dumps(result["parity"]))
    return cast(dict[str, Any], result)


def _manifest_row(
    record: dict[str, Any], dispositions: dict[str, SeatDisposition]
) -> dict[str, Any]:
    source_seat = str(record.get("seat", "unknown-owner"))
    disposition = dispositions.get(
        source_seat, SeatDisposition(source_seat, "source_only", None)
    )
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "source_ref", "content_sha256"}
    }
    return {
        "_disposition": disposition.disposition,
        "content_sha256": record["content_sha256"],
        "natural_key": f"escape:{record['record_id']}",
        "source_ref": record["source_ref"],
        "source_seat": source_seat,
        "target_seat_key": disposition.target_seat_key,
        "payload": payload,
    }


def _request_row(record: dict[str, Any]) -> dict[str, Any]:
    occurred_on = str(record.get("date") or record.get("ts", ""))[:10]
    date.fromisoformat(occurred_on)
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "source_ref", "content_sha256"}
    }
    return {
        "schema": "ctower.company-record-import/v1",
        "record_type": "escape",
        "natural_key": f"escape:{record['record_id']}",
        "occurred_on": occurred_on,
        "payload": payload,
        "source_ref": record["source_ref"],
        "seat": str(record.get("seat", "source-only")),
        "imported_at": datetime.now(UTC).isoformat(),
    }


def _load_dispositions(path: Path | None) -> dict[str, SeatDisposition]:
    if path is None:
        return {}
    return load_seat_mapping(path)


def _mapping_digest(path: Path | None) -> str | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return cast(str, value["mapping_digest"])


def _ineligible(
    error: str, project_key: str, *, escapes_count: int | None = None
) -> dict[str, Any]:
    return {
        "schema": "ctower.company-records-import-dry-run/v1",
        "mode": "DRY-RUN",
        "eligible": False,
        "error": error,
        "project_key": project_key,
        "writes_attempted": 0,
        **({"escapes_count": escapes_count} if escapes_count is not None else {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC escapes/company-records import")
    parser.add_argument("--escapes", required=True, type=Path)
    parser.add_argument("--project", default="ctower")
    parser.add_argument("--seat-map", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    report = analyze_escapes_import(
        args.escapes,
        project_key=args.project,
        seat_map_path=args.seat_map,
    )
    if args.manifest_output and isinstance(report.get("manifest"), dict):
        args.manifest_output.write_bytes(rfc8785.dumps(report["manifest"]))
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["eligible"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
