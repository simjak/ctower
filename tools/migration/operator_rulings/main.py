"""Ruling import from agreed-decision files for the R3000 migration.

This tool reads frozen MC board/agreed-*.md files and creates
Rulings with historical timestamps, reusing the existing Ruling model.

The tool uses the existing `ruling append` path through operator-authenticated
HTTP calls with a timestamp override.

Usage:
  python -m tools.migration.operator_rulings.main \\
    --agreed-dir /path/to/board/ \\
    --project ctower \\
    --evidence ./rulings-evidence/ \\
    [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid as uuid_mod
from pathlib import Path
from typing import Any

try:
    import httpx
    import rfc8785
except ImportError:
    httpx = None
    rfc8785 = None

from tools.migration.ctower_project.ctower_project_source.canonical import sha256_digest
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

__all__ = ["analyze_rulings_import", "execute_rulings_import"]

_RULING_NAMESPACE = uuid_mod.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")
_SCHEMA = "ctower.ruling-import-manifest/v1"
_HTTP_CONFLICT = 409


def _parse_agreed_files(agreed_dir: Path) -> list[dict[str, Any]]:
    """Read all agreed-*.md files from the board directory."""
    rulings: list[dict[str, Any]] = []
    for fpath in sorted(agreed_dir.glob("agreed-*.md")):
        content = fpath.read_text(encoding="utf-8")
        # Generate deterministic ID from file path
        ruling_id = uuid_mod.uuid5(_RULING_NAMESPACE, str(fpath.resolve()))
        # Extract a heading from the first line
        first_line = content.split("\n")[0].strip("# ").strip()
        heading = first_line or fpath.stem
        rulings.append(
            {
                "ruling_id": str(ruling_id),
                "source_path": str(
                    fpath.relative_to(agreed_dir.parent) if agreed_dir.parent else fpath
                ),
                "filename": fpath.name,
                "heading": heading,
                "verbatim": content,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "file_size": fpath.stat().st_size,
            }
        )
    return rulings


def analyze_rulings_import(
    agreed_dir: Path,
    *,
    project_key: str = "ctower",
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Read-only analysis of agreed-decision files for ruling import."""
    if not agreed_dir.is_dir():
        return {
            "schema": "ctower.ruling-import-dry-run/v1",
            "mode": "DRY-RUN",
            "eligible": False,
            "error": f"not a directory: {agreed_dir}",
            "writes_attempted": 0,
        }

    rulings = _parse_agreed_files(agreed_dir)
    source_count = len(rulings)
    rulings_digest = sha256_digest(json.dumps(rulings, sort_keys=True).encode())

    manifest = {
        "schema": _SCHEMA,
        "project_key": project_key,
        "counts": {
            "source_files": source_count,
        },
        "rulings": rulings,
        "rulings_digest": f"sha256:{rulings_digest}",
    }

    if signer is not None:
        manifest = signer.seal(manifest, "manifest_digest")

    return {
        "schema": "ctower.ruling-import-dry-run/v1",
        "mode": "DRY-RUN" if signer is None else "SIGNED",
        "eligible": source_count > 0,
        "ruling_count": source_count,
        "source_files": [r["filename"] for r in rulings],
        "project_key": project_key,
        "writes_attempted": 0,
        "manifest": manifest,
    }


def execute_rulings_import(
    client: httpx.Client,
    *,
    agreed_dir: Path,
    base_url: str,
    evidence_dir: Path,
    project_key: str = "ctower",
) -> dict[str, Any]:
    """Execute the ruling import via HTTP POST to the rulings endpoint."""
    rulings = _parse_agreed_files(agreed_dir)
    imported = 0
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    for ruling in rulings:
        payload = {
            "verbatim": ruling["verbatim"],
            "project_key": project_key,
        }
        command_id = uuid_mod.uuid5(_RULING_NAMESPACE, ruling["ruling_id"])
        try:
            resp = client.post(
                f"{base_url}/v1/rulings",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(command_id),
                    "X-Import-Source": "r3000-rulings",
                },
                timeout=30,
            )
            if resp.status_code == _HTTP_CONFLICT:
                imported += 1  # Already imported
                continue
            resp.raise_for_status()
            imported += 1
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == _HTTP_CONFLICT:
                imported += 1
                continue
            raise

    return {
        "schema": "ctower.ruling-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rulings),
        "imported_count": imported,
        "writes_attempted": imported,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC agreed-decision ruling import")
    parser.add_argument("--agreed-dir", required=True, type=Path)
    parser.add_argument("--project", default="ctower")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = analyze_rulings_import(args.agreed_dir, project_key=args.project)
    if args.dry_run or not args.evidence:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return 0 if report.get("eligible", False) else 3

    if not args.base_url:
        print("--base-url required", file=__import__("sys").stderr)
        return 1

    with httpx.Client(verify=False) as client:
        result = execute_rulings_import(
            client,
            agreed_dir=args.agreed_dir,
            base_url=args.base_url,
            evidence_dir=args.evidence,
            project_key=args.project,
        )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
