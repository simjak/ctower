"""Operator-authority import planning for Mission Control escape records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

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
_BATCH_SIZE = 100
_HTTP_CONFLICT = 409


class _ImportResponse(Protocol):
    status_code: int

    def raise_for_status(self) -> None: ...

    def json(self) -> dict[str, object]: ...


class _ImportClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: Mapping[str, str],
        timeout: float,
    ) -> _ImportResponse: ...


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
    client: _ImportClient,
    *,
    escapes_path: Path,
    manifest: dict[str, Any],
    base_url: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    """Send signed, bounded company-record batches through the API seam."""

    records = _parse_escapes(escapes_path)
    rows = [_request_row(record) for record in records]
    batches = manifest.get("batches")
    manifest_digest = manifest.get("manifest_digest")
    if not isinstance(batches, list) or not batches or not isinstance(manifest_digest, str):
        raise ValueError("company-record manifest has no complete batches")
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    imported = 0
    results: list[dict[str, object]] = []
    offset = 0
    for expected_index, batch in enumerate(batches):
        count = _batch_count(batch, expected_index)
        current = rows[offset : offset + count]
        if len(current) != count:
            raise ValueError("manifest company-record batches do not cover the frozen source")
        result = _post_batch(
            client,
            base_url=base_url,
            manifest=manifest,
            manifest_digest=manifest_digest,
            batch_index=expected_index,
            rows=current,
        )
        batch_imported = result.get("imported_count")
        if not isinstance(batch_imported, int) or not 0 <= batch_imported <= count:
            raise ValueError("company-record import response has an invalid imported count")
        imported += batch_imported
        results.append(result)
        _write_parity(evidence_dir, expected_index, result)
        offset += count
    if offset != len(rows):
        raise ValueError("manifest company-record batches do not cover the frozen source")
    evidence_dir.joinpath("results.json").write_bytes(rfc8785.dumps(cast(Any, results)))
    return {
        "schema": "ctower.company-records-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rows),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": len(batches),
        "evidence_dir": str(evidence_dir),
        "results": results,
    }


def _batch_count(batch: object, expected_index: int) -> int:
    if not isinstance(batch, Mapping) or batch.get("batch_index") != expected_index:
        raise ValueError("manifest company-record batches are not contiguous")
    count = batch.get("source_count")
    if not isinstance(count, int) or not 1 <= count <= _BATCH_SIZE:
        raise ValueError("manifest company-record batch count is invalid")
    return count


def _post_batch(
    client: _ImportClient,
    *,
    base_url: str,
    manifest: dict[str, Any],
    manifest_digest: str,
    batch_index: int,
    rows: list[dict[str, Any]],
) -> dict[str, object]:
    command_id = uuid5(
        _ESCAPE_NAMESPACE,
        f"estate-company-records:{manifest_digest}:{batch_index}",
    )
    response = client.post(
        f"{base_url}/v1/migrations/estate/company-records",
        json={"manifest": manifest, "batch_index": batch_index, "rows": rows},
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
        },
        timeout=60,
    )
    if response.status_code == _HTTP_CONFLICT:
        return response.json()
    response.raise_for_status()
    return response.json()


def _write_parity(evidence_dir: Path, batch_index: int, result: Mapping[str, object]) -> None:
    parity = result.get("parity")
    if isinstance(parity, Mapping):
        evidence_dir.joinpath(f"batch-{batch_index:04d}.parity.json").write_bytes(
            rfc8785.dumps(cast(Any, parity))
        )


def _manifest_row(
    record: dict[str, Any], dispositions: dict[str, SeatDisposition]
) -> dict[str, Any]:
    source_seat = str(record.get("seat", "unknown-owner"))
    disposition = dispositions.get(source_seat, SeatDisposition(source_seat, "source_only", None))
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
