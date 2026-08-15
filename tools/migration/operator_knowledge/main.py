"""Operator-authority import planning for historical knowledge documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import build_estate_manifest, stable_source_id

__all__ = ["analyze_knowledge_import", "execute_knowledge_import"]

_TIER = "knowledge_documents"
_BATCH_SIZE = 100
_BATCH_NAMESPACE = UUID("c4d5e6f7-a8b9-4012-cdef-234567890123")


def _parse_knowledge_files(root: Path) -> list[dict[str, Any]]:
    """Read policy/reference Markdown while leaving agreed decisions to Rulings."""

    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.md")):
        if path.is_symlink() or not path.is_file() or path.name.startswith("agreed-"):
            continue
        relative = path.relative_to(root).as_posix()
        body = path.read_text(encoding="utf-8")
        content_digest = f"sha256:{hashlib.sha256(body.encode('utf-8')).hexdigest()}"
        rows.append(
            {
                "document_id": str(stable_source_id(_TIER, relative)),
                "source_ref": relative,
                "title": _title(path, body),
                "body": body,
                "recorded_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
                "content_sha256": content_digest,
            }
        )
    return rows


def analyze_knowledge_import(
    root: Path,
    *,
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Build a source-bound manifest without writing or closing the source."""

    if not root.is_dir():
        return _ineligible(f"not a directory: {root}")
    rows = _parse_knowledge_files(root)
    if not rows:
        return _ineligible("source is empty", document_count=0)
    source_digest = _source_digest(rows)
    estate_rows = [
        {
            "_disposition": "source_only",
            "content_sha256": row["content_sha256"],
            "source_ref": row["source_ref"],
            "source_seat": "unknown-owner",
        }
        for row in rows
    ]
    manifest = build_estate_manifest(
        tier=_TIER,
        source_identity={
            "namespace": "mission-control:estate",
            "source_path": str(root.resolve()),
            "source_sha256": source_digest,
        },
        rows=estate_rows,
        seat_mapping_digest=None,
        signer=signer,
    )
    return {
        "schema": "ctower.knowledge-import-dry-run/v1",
        "mode": "SIGNED" if signer is not None else "DRY-RUN",
        "eligible": True,
        "document_count": len(rows),
        "writes_attempted": 0,
        "rows": rows,
        "estate_manifest": manifest,
        "estate_rows": estate_rows,
    }


def execute_knowledge_import(
    client: httpx.Client,
    *,
    root: Path,
    manifest: dict[str, Any],
    base_url: str,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Send each signed knowledge batch through the operator-only API seam."""
    rows = _parse_knowledge_files(root)
    batches = manifest.get("batches")
    manifest_digest = manifest.get("manifest_digest")
    if not isinstance(batches, list) or not batches or not isinstance(manifest_digest, str):
        raise ValueError("knowledge manifest has no complete batches")
    if evidence_dir is not None:
        evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    imported, results = _post_knowledge_batches(
        client,
        base_url=base_url,
        manifest=manifest,
        manifest_digest=manifest_digest,
        rows=rows,
        batches=batches,
        evidence_dir=evidence_dir,
    )
    if evidence_dir is not None:
        evidence_dir.joinpath("results.json").write_bytes(rfc8785.dumps(cast(Any, results)))
    return {
        "schema": "ctower.knowledge-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rows),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": len(batches),
        "evidence_dir": None if evidence_dir is None else str(evidence_dir),
        "results": results,
    }


def _post_knowledge_batches(
    client: httpx.Client,
    *,
    base_url: str,
    manifest: dict[str, Any],
    manifest_digest: str,
    rows: list[dict[str, Any]],
    batches: list[object],
    evidence_dir: Path | None,
) -> tuple[int, list[dict[str, Any]]]:
    imported = 0
    offset = 0
    results: list[dict[str, Any]] = []
    for expected_index, batch in enumerate(batches):
        count = _knowledge_batch_count(batch, expected_index)
        current = rows[offset : offset + count]
        if len(current) != count:
            raise ValueError("manifest knowledge batches do not cover the frozen source")
        result = _post_knowledge_batch(
            client,
            base_url=base_url,
            manifest=manifest,
            manifest_digest=manifest_digest,
            batch_index=expected_index,
            rows=current,
        )
        batch_imported = result.get("imported_count")
        if not isinstance(batch_imported, int) or not 0 <= batch_imported <= count:
            raise ValueError("knowledge import response has an invalid imported count")
        imported += batch_imported
        results.append(result)
        _write_parity(evidence_dir, expected_index, result)
        offset += count
    if offset != len(rows):
        raise ValueError("manifest knowledge batches do not cover the frozen source")
    return imported, results


def _knowledge_batch_count(batch: object, expected_index: int) -> int:
    if not isinstance(batch, Mapping) or batch.get("batch_index") != expected_index:
        raise ValueError("manifest knowledge batches are not contiguous")
    count = batch.get("source_count")
    if not isinstance(count, int) or not 1 <= count <= _BATCH_SIZE:
        raise ValueError("manifest knowledge batch count is invalid")
    return count


def _post_knowledge_batch(
    client: httpx.Client,
    *,
    base_url: str,
    manifest: dict[str, Any],
    manifest_digest: str,
    batch_index: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    command_id = uuid5(
        _BATCH_NAMESPACE,
        f"estate-knowledge:{manifest_digest}:{batch_index}",
    )
    response = client.post(
        f"{base_url}/v1/migrations/estate/knowledge",
        json={"manifest": manifest, "batch_index": batch_index, "rows": rows},
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
        },
        timeout=60,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _write_parity(
    evidence_dir: Path | None,
    batch_index: int,
    result: dict[str, Any],
) -> None:
    parity = result.get("parity")
    if evidence_dir is not None and isinstance(parity, dict):
        evidence_dir.joinpath(f"batch-{batch_index:04d}.parity.json").write_bytes(
            rfc8785.dumps(cast(Any, parity))
        )


def _title(path: Path, body: str) -> str:
    first = body.splitlines()[0].removeprefix("#").strip() if body.splitlines() else ""
    return first or path.stem


def _source_digest(rows: list[dict[str, Any]]) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, rows))).hexdigest()}"


def _ineligible(error: str, *, document_count: int = 0) -> dict[str, Any]:
    return {
        "schema": "ctower.knowledge-import-dry-run/v1",
        "mode": "DRY-RUN",
        "eligible": False,
        "document_count": document_count,
        "error": error,
        "writes_attempted": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC knowledge-document import")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args(argv)
    report = analyze_knowledge_import(args.root)
    if args.manifest_output and isinstance(report.get("estate_manifest"), dict):
        args.manifest_output.write_bytes(rfc8785.dumps(report["estate_manifest"]))
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["eligible"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
