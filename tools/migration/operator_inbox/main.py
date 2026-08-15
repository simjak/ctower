"""Inbox import from frozen MC inbox.jsonl — per the 0059 pattern.

This tool reads the frozen mission-control inbox.jsonl, maps MC
sender/recipient seat names to ctower seats, and submits signed, bounded
batches through the operator-only estate-import HTTP boundary.

Usage:
  python -m tools.migration.operator_inbox.main \
    --ledger /path/to/inbox.jsonl \
    --seat-map /path/to/seat-mapping.json \
    --project ctower \
    --manifest-output /operator-evidence/inbox-manifest.json \
    --evidence /operator-evidence/inbox/ \
    --base-url https://ctower.example \
    [--dry-run]

Dedup: deterministic UUIDv5 from (timestamp, sender, project, subject).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.canonical import (
    sha256_digest,
    strict_json,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.estate_imports import (
    build_estate_manifest,
    load_seat_mapping,
    read_stable_source,
)

__all__ = ["analyze_inbox_import", "execute_inbox_import"]

_INBOX_NAMESPACE = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_BATCH_SIZE = 100
_SCHEMA = "ctower.inbox-import-manifest/v1"


class _ImportResponse(Protocol):
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


class _ArtifactVerifier(Protocol):
    def verify(self, artifact: dict[str, Any], digest_field: str) -> None: ...


class _ArtifactVerifierProvider(Protocol):
    def verifier(self) -> _ArtifactVerifier: ...


# ---- Source parsing -------------------------------------------------------


def _parse_inbox_jsonl(ledger_path: Path) -> list[dict[str, Any]]:
    """Parse MC's ``LINENUM:{...}`` or plain-object JSONL format."""
    result: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        ledger_path.read_bytes().decode("utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line and line[0].isdigit():
            _, _, line = line.partition(":")
            line = line.strip()
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"inbox row {line_number} is not a JSON object")
        result.append(cast(dict[str, Any], value))
    return result


def _extract_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one MC row while retaining the source recipient identity."""
    ts = row.get("ts", "")
    from_seat = row.get("from", "unknown")
    to_seat = row.get("to") or row.get("recipient") or "operator"
    project = row.get("project", "unknown")
    subject = row.get("subject", "")
    body = row.get("body", "")
    read_flag = row.get("read", False)
    dedup_key = f"{ts}:{from_seat}:{project}:{subject}"
    message_id = uuid5(_INBOX_NAMESPACE, dedup_key)

    return {
        "message_id": str(message_id),
        "ts": ts,
        "from": from_seat,
        "to": to_seat,
        "project": project,
        "subject": subject,
        "body": body,
        "read": read_flag,
        "content_sha256": hashlib.sha256(
            json.dumps({"subject": subject, "body": body}, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


# ---- Analysis / dry run --------------------------------------------------


def analyze_inbox_import(
    ledger_path: Path,
    *,
    seat_map_path: Path | None = None,
    project_key: str = "ctower",
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Read-only analysis: derive legacy and estate manifests without writes."""
    if not ledger_path.exists():
        raise FileNotFoundError(ledger_path)
    source_bytes, source_identity = read_stable_source(ledger_path)
    ledger_digest = sha256_digest(source_bytes)
    physical = _parse_inbox_jsonl(ledger_path)
    rows = [_extract_fields(row) for row in physical]
    source_count = len(rows)
    source_sha256 = hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
    seat_map = _load_seat_map(seat_map_path)
    batches = _legacy_batches(rows)
    legacy_manifest: dict[str, Any] = {
        "schema": _SCHEMA,
        "ledger_sha256": f"sha256:{source_sha256}",
        "source_identity": source_identity,
        "project_key": project_key,
        "counts": {"physical_rows": source_count, "logical_messages": source_count},
        "maximum_message_number": source_count,
        "batches": batches,
    }
    unknown_seats = sorted({str(row["from"]) for row in rows if row["from"] not in seat_map})
    import_rows = _estate_rows(rows, ledger_path, seat_map)
    estate_manifest = build_estate_manifest(
        tier="inbox_history",
        source_identity=source_identity,
        rows=import_rows,
        seat_mapping_digest=_mapping_digest(seat_map_path),
        signer=signer,
    )
    if signer is not None:
        legacy_manifest = signer.seal(legacy_manifest, "manifest_digest")
    return {
        "schema": "ctower.inbox-import-dry-run/v1",
        "mode": "DRY-RUN" if signer is None else "SIGNED",
        "eligible": source_count > 0,
        "ledger_digest": ledger_digest,
        "row_count": source_count,
        "batch_count": len(batches),
        "unknown_from_seats": unknown_seats,
        "unknown_seat_count": len(unknown_seats),
        "project_key": project_key,
        "writes_attempted": 0,
        "manifest": legacy_manifest,
        "estate_manifest": estate_manifest,
        "estate_rows": import_rows,
    }


def _legacy_batches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(rows), _BATCH_SIZE):
        current = rows[offset : offset + _BATCH_SIZE]
        batches.append(
            {
                "batch_index": offset // _BATCH_SIZE,
                "batch_digest": sha256_digest(json.dumps(current, sort_keys=True).encode("utf-8")),
                "source_count": len(current),
                "cumulative_count": min(offset + _BATCH_SIZE, len(rows)),
                "sample_ids": [row["message_id"] for row in current[:3]],
            }
        )
    return batches


def _estate_rows(
    rows: list[dict[str, Any]], ledger_path: Path, seat_map: dict[str, str]
) -> list[dict[str, Any]]:
    return [
        {
            "_disposition": "mapped" if row["from"] in seat_map else "source_only",
            "content_sha256": f"sha256:{row['content_sha256']}",
            "source_ref": f"{ledger_path.name}#{index}",
            "source_seat": str(row["from"]),
            "target_seat_key": seat_map.get(str(row["from"])),
        }
        for index, row in enumerate(rows, 1)
    ]


def _load_seat_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    loaded = strict_json(path.read_bytes(), context="seat map")
    if isinstance(loaded, dict) and loaded.get("schema") == "ctower.estate-seat-mapping/v1":
        return {
            source: str(item.target_seat_key)
            for source, item in load_seat_mapping(path).items()
            if item.disposition == "mapped" and item.target_seat_key is not None
        }
    if not isinstance(loaded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in loaded.items()
    ):
        raise ValueError("seat map must be an object of source-seat to target-seat strings")
    return cast(dict[str, str], loaded)


def _mapping_digest(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value.get("mapping_digest") if isinstance(value, dict) else None


# ---- Execution ------------------------------------------------------------


def execute_inbox_import(
    client: _ImportClient,
    *,
    ledger_path: Path,
    manifest_path: Path,
    evidence_dir: Path,
    signer: _ArtifactVerifierProvider,
    base_url: str,
) -> dict[str, Any]:
    """Submit one signed estate-manifest batch per bounded source batch."""
    manifest, rows, batches = _load_execution_input(ledger_path, manifest_path, signer)
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    imported = 0
    batch_results: list[dict[str, object]] = []
    offset = 0
    for expected_index, batch in enumerate(batches):
        count, current = _batch_slice(batch, expected_index, rows, offset)
        result = _post_batch(
            client,
            base_url=base_url,
            manifest=manifest,
            batch_index=expected_index,
            rows=current,
            offset=offset,
        )
        batch_results.append(result)
        imported += _imported_count(result)
        _write_batch_evidence(evidence_dir, expected_index, result)
        offset += count
    if offset != len(rows):
        raise ValueError("manifest batches do not cover the frozen source")
    (evidence_dir / "results.json").write_bytes(rfc8785.dumps(cast(Any, batch_results)))
    return {
        "schema": "ctower.inbox-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rows),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": len(batches),
        "evidence_dir": str(evidence_dir),
        "results": batch_results,
    }


def _load_execution_input(
    ledger_path: Path,
    manifest_path: Path,
    signer: _ArtifactVerifierProvider,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = _signed_artifact(manifest_path, signer, "manifest_digest")
    if manifest.get("schema") != "ctower.estate-import-manifest/v1":
        raise ValueError("manifest is not an estate import manifest")
    if manifest.get("tier") != "inbox_history":
        raise ValueError("manifest tier is not inbox_history")
    source_bytes = ledger_path.read_bytes()
    source_identity = manifest.get("source_identity")
    if not isinstance(source_identity, dict) or source_identity.get(
        "source_sha256"
    ) != sha256_digest(source_bytes):
        raise ValueError("frozen inbox source does not match the signed manifest")
    rows = [_extract_fields(row) for row in _parse_inbox_jsonl(ledger_path)]
    counts = manifest.get("counts")
    batches = manifest.get("batches")
    if not isinstance(counts, dict) or counts.get("source_rows") != len(rows):
        raise ValueError("manifest source count does not match the frozen source")
    if not isinstance(batches, list) or not batches:
        raise ValueError("manifest has no batches")
    return manifest, rows, cast(list[dict[str, Any]], batches)


def _batch_slice(
    batch: object,
    expected_index: int,
    rows: list[dict[str, Any]],
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    if not isinstance(batch, dict):
        raise TypeError("manifest batch is not an object")
    if batch.get("batch_index") != expected_index:
        raise ValueError("manifest batches are not contiguous")
    count = batch.get("source_count")
    if not isinstance(count, int):
        raise TypeError("manifest batch source count is not an integer")
    if count < 1:
        raise ValueError("manifest batch source count is invalid")
    current = rows[offset : offset + count]
    if len(current) != count:
        raise ValueError("manifest batch counts exceed the frozen source")
    return count, current


def _write_batch_evidence(
    evidence_dir: Path, batch_index: int, result: Mapping[str, object]
) -> None:
    parity = result.get("parity")
    if isinstance(parity, dict):
        (evidence_dir / f"batch-{batch_index:04d}.parity.json").write_bytes(
            rfc8785.dumps(cast(Any, parity))
        )


def _post_batch(
    client: _ImportClient,
    *,
    base_url: str,
    manifest: dict[str, Any],
    batch_index: int,
    rows: list[dict[str, Any]],
    offset: int,
) -> dict[str, object]:
    import_rows = [_request_row(row, offset + index) for index, row in enumerate(rows, 1)]
    batch_command_id = uuid5(
        _INBOX_NAMESPACE,
        f"estate-inbox:{manifest['manifest_digest']}:{batch_index}",
    )
    response = client.post(
        f"{base_url}/v1/migrations/estate/inbox",
        json={
            "manifest": manifest,
            "batch_index": batch_index,
            "rows": import_rows,
        },
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(batch_command_id),
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _imported_count(result: Mapping[str, object]) -> int:
    value = result.get("imported_count")
    if not isinstance(value, int) or value < 0:
        raise ValueError("import response has an invalid imported count")
    return value


def _request_row(row: dict[str, Any], line_number: int) -> dict[str, Any]:
    return {
        "message_id": row["message_id"],
        "source_ref": f"inbox.jsonl#{line_number}",
        "source_sender": row["from"],
        "source_recipient": row["to"],
        "sent_at": row["ts"],
        "subject": row["subject"],
        "body": row["body"],
        "read_state": "read" if row["read"] else "delivered",
        "content_sha256": f"sha256:{row['content_sha256']}",
    }


# ---- CLI ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC inbox import into ctower")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--seat-map", type=Path)
    parser.add_argument("--project", default="ctower")
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--signing-key-map", type=Path)
    parser.add_argument("--signing-key-ref")
    parser.add_argument("--signing-key-version", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    signer = _signer(args)
    report = analyze_inbox_import(
        args.ledger,
        seat_map_path=args.seat_map,
        project_key=args.project,
        signer=signer,
    )
    if args.dry_run or not args.evidence:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        if args.manifest_output and isinstance(report.get("estate_manifest"), dict):
            args.manifest_output.write_bytes(rfc8785.dumps(cast(Any, report["estate_manifest"])))
        return 0 if report["eligible"] else 3
    if not args.base_url:
        print("--base-url required for non-dry-run mode", file=__import__("sys").stderr)
        return 1
    if not args.manifest_output:
        print("--manifest-output required for non-dry-run mode", file=__import__("sys").stderr)
        return 1
    if signer is None:
        print("signing args required for non-dry-run mode", file=__import__("sys").stderr)
        return 1
    with httpx.Client() as client:
        result = execute_inbox_import(
            cast(_ImportClient, client),
            ledger_path=args.ledger,
            manifest_path=args.manifest_output,
            evidence_dir=args.evidence,
            signer=cast(_ArtifactVerifierProvider, signer),
            base_url=args.base_url,
        )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


_HTTP_CONFLICT = 409


def _signer(args: argparse.Namespace) -> ArtifactSigner | None:
    keys = (args.signing_key_map, args.signing_key_ref, args.signing_key_version)
    if all(value is None for value in keys):
        return None
    if any(value is None for value in keys):
        raise ValueError("signing arguments must be supplied together")
    return ArtifactSigner.from_reference_map(
        args.signing_key_map,
        args.signing_key_ref,
        key_version=args.signing_key_version,
    )


def _signed_artifact(
    path: Path, signer: _ArtifactVerifierProvider, digest_field: str
) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("manifest must be a JSON object")
    artifact = cast(dict[str, Any], raw)
    signer.verifier().verify(artifact, digest_field)
    return artifact


if __name__ == "__main__":
    raise SystemExit(main())
