"""Operator-authority import planning for historical knowledge documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import build_estate_manifest, stable_source_id

__all__ = ["analyze_knowledge_import", "execute_knowledge_import"]

_TIER = "knowledge_documents"


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
) -> dict[str, Any]:
    """Send one signed knowledge batch through the operator-only API seam."""

    response = client.post(
        f"{base_url}/v1/migrations/estate/knowledge",
        json={"manifest": manifest, "rows": _parse_knowledge_files(root)},
        timeout=60,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


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
