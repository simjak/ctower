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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

try:
    import httpx
    import rfc8785
except ImportError:
    httpx = None  # type: ignore[assignment]
    rfc8785 = None  # type: ignore[assignment]

from tools.migration.ctower_project.ctower_project_source.canonical import sha256_digest
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import build_estate_manifest

__all__ = ["analyze_rulings_import", "execute_rulings_import"]

_RULING_NAMESPACE = uuid_mod.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")
_SCHEMA = "ctower.ruling-import-manifest/v1"
_HTTP_CONFLICT = 409
_BATCH_SIZE = 100


def _parse_agreed_files(agreed_dir: Path) -> list[dict[str, Any]]:
    """Read all agreed-*.md files from the board directory."""
    rulings: list[dict[str, Any]] = []
    for fpath in sorted(agreed_dir.glob("agreed-*.md")):
        content = fpath.read_text(encoding="utf-8")
        source_ref = fpath.relative_to(agreed_dir).as_posix()
        # Generate deterministic identity from the frozen source-relative reference.
        ruling_id = uuid_mod.uuid5(_RULING_NAMESPACE, source_ref)
        # Extract a heading from the first line
        first_line = content.split("\n")[0].strip("# ").strip()
        heading = first_line or fpath.stem
        rulings.append(
            {
                "ruling_id": str(ruling_id),
                "source_path": source_ref,
                "filename": fpath.name,
                "heading": heading,
                "verbatim": content,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "file_size": fpath.stat().st_size,
                "recorded_at": datetime.fromtimestamp(fpath.stat().st_mtime, tz=UTC).isoformat(),
                "source_ref": source_ref,
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

    estate_rows = [
        {
            "_disposition": "source_only",
            "content_sha256": f"sha256:{ruling['content_sha256']}",
            "source_ref": ruling["source_ref"],
            "source_seat": "unknown-owner",
        }
        for ruling in rulings
    ]
    estate_manifest = (
        build_estate_manifest(
            tier="agreed_decisions",
            source_identity={
                "namespace": "mission-control:estate",
                "source_path": str(agreed_dir.resolve()),
                "source_sha256": f"sha256:{rulings_digest}",
            },
            rows=estate_rows,
            seat_mapping_digest=None,
            signer=signer,
        )
        if estate_rows
        else None
    )

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
        "estate_manifest": estate_manifest,
        "estate_rows": estate_rows,
    }


def execute_rulings_import(
    client: httpx.Client,
    *,
    agreed_dir: Path,
    base_url: str,
    evidence_dir: Path,
    project_key: str = "ctower",
    manifest_path: Path | None = None,
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Submit signed, bounded ruling estate batches through the import seam."""
    del project_key
    rulings = _parse_agreed_files(agreed_dir)
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest = _execution_manifest(
        agreed_dir,
        rulings,
        manifest_path=manifest_path,
        signer=signer,
    )
    batches = manifest.get("batches")
    if not isinstance(batches, list) or not batches:
        raise ValueError("manifest has no ruling batches")
    manifest_digest = manifest.get("manifest_digest")
    if not isinstance(manifest_digest, str):
        raise TypeError("manifest has no digest")
    imported, results = _post_ruling_batches(
        client,
        base_url=base_url,
        manifest=manifest,
        manifest_digest=manifest_digest,
        rulings=rulings,
        batches=batches,
        evidence_dir=evidence_dir,
    )

    transcript = {
        "schema": "ctower.ruling-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rulings),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": len(batches),
        "evidence_dir": str(evidence_dir),
        "results": results,
    }
    (evidence_dir / "results.json").write_bytes(rfc8785.dumps(cast(Any, results)))
    return transcript


def _post_ruling_batches(
    client: httpx.Client,
    *,
    base_url: str,
    manifest: dict[str, Any],
    manifest_digest: str,
    rulings: list[dict[str, Any]],
    batches: list[object],
    evidence_dir: Path,
) -> tuple[int, list[dict[str, object]]]:
    imported = 0
    offset = 0
    results: list[dict[str, object]] = []
    for expected_index, batch in enumerate(batches):
        count = _ruling_batch_count(batch, expected_index)
        current = rulings[offset : offset + count]
        if len(current) != count:
            raise ValueError("manifest ruling batches do not cover the frozen source")
        result = _post_ruling_batch(
            client,
            base_url=base_url,
            manifest=manifest,
            manifest_digest=manifest_digest,
            batch_index=expected_index,
            rows=_ruling_rows(current),
        )
        imported_count = result.get("imported_count")
        if not isinstance(imported_count, int) or not 0 <= imported_count <= count:
            raise ValueError("ruling import response has an invalid imported count")
        imported += imported_count
        results.append(result)
        _write_parity(evidence_dir, expected_index, result)
        offset += count
    if offset != len(rulings):
        raise ValueError("manifest ruling batches do not cover the frozen source")
    return imported, results


def _ruling_batch_count(batch: object, expected_index: int) -> int:
    if not isinstance(batch, dict) or batch.get("batch_index") != expected_index:
        raise ValueError("manifest ruling batches are not contiguous")
    count = batch.get("source_count")
    if not isinstance(count, int) or not 1 <= count <= _BATCH_SIZE:
        raise ValueError("manifest ruling batch count is invalid")
    return count


def _ruling_rows(current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_ref": ruling["source_ref"],
            "verbatim": ruling["verbatim"],
            "recorded_at": ruling["recorded_at"],
            "content_sha256": f"sha256:{ruling['content_sha256']}",
        }
        for ruling in current
    ]


def _post_ruling_batch(
    client: httpx.Client,
    *,
    base_url: str,
    manifest: dict[str, Any],
    manifest_digest: str,
    batch_index: int,
    rows: list[dict[str, Any]],
) -> dict[str, object]:
    command_id = uuid_mod.uuid5(
        _RULING_NAMESPACE,
        f"estate-rulings:{manifest_digest}:{batch_index}",
    )
    response = client.post(
        f"{base_url}/v1/migrations/estate/rulings",
        json={"manifest": manifest, "batch_index": batch_index, "rows": rows},
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
        },
        timeout=60,
    )
    if response.status_code == _HTTP_CONFLICT:
        return cast(dict[str, object], response.json())
    response.raise_for_status()
    return cast(dict[str, object], response.json())


def _write_parity(evidence_dir: Path, batch_index: int, result: dict[str, object]) -> None:
    parity = result.get("parity")
    if isinstance(parity, dict):
        evidence_dir.joinpath(f"batch-{batch_index:04d}.parity.json").write_bytes(
            rfc8785.dumps(cast(Any, parity))
        )


def _execution_manifest(
    agreed_dir: Path,
    rulings: list[dict[str, Any]],
    *,
    manifest_path: Path | None,
    signer: ArtifactSigner | None,
) -> dict[str, Any]:
    if manifest_path is not None:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("ruling manifest must be an object")
        manifest = cast(dict[str, Any], raw)
        if signer is None:
            raise ValueError("a signer verifier is required for manifest execution")
        signer.verifier().verify(manifest, "manifest_digest")
        return manifest
    estate_rows = [
        {
            "_disposition": "source_only",
            "content_sha256": f"sha256:{ruling['content_sha256']}",
            "source_ref": ruling["source_ref"],
            "source_seat": "unknown-owner",
        }
        for ruling in rulings
    ]
    return build_estate_manifest(
        tier="agreed_decisions",
        source_identity={
            "namespace": "mission-control:estate",
            "source_path": str(agreed_dir.resolve()),
            "source_sha256": (
                f"sha256:{sha256_digest(json.dumps(rulings, sort_keys=True).encode())}"
            ),
        },
        rows=estate_rows,
        seat_mapping_digest=None,
        signer=signer,
    )


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
