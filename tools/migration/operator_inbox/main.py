"""Inbox import from frozen MC inbox.jsonl — per the 0059 pattern.

This tool reads the frozen mission-control inbox.jsonl (10,417 rows),
maps MC sender/recipient seat names to ctower principal IDs,
and executes the import through the existing authenticated inbox send
path with operator authority.

Usage:
  python -m tools.migration.operator_inbox.main \\
    --ledger /path/to/inbox.jsonl \\
    --seat-map /path/to/seat-mapping.json \\
    --project ctower \\
    --evidence ./inbox-evidence/ \\
    [--dry-run]

Dedup: deterministic UUIDv5 from (ts, from, project, subject).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.canonical import (
    sha256_digest,
    strict_json,
)
from tools.migration.ctower_project.ctower_project_source.signing import (
    ArtifactSigner,
)
from tools.migration.estate_imports import (
    build_estate_manifest,
    load_seat_mapping,
    read_stable_source,
)

__all__ = ["analyze_inbox_import", "execute_inbox_import"]

_INBOX_NAMESPACE = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_BATCH_SIZE = 100
_SCHEMA = "ctower.inbox-import-manifest/v1"


# ---- Source parsing ----


def _parse_inbox_jsonl(ledger_path: Path) -> list[dict[str, Any]]:
    """Parse the MC inbox.jsonl format (LINENUM:{...} or plain {...})."""
    raw = ledger_path.read_bytes()
    text = raw.decode("utf-8")
    result: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip leading line number if present (MC format: "1:{...}")
        if ":" in line and line[0].isdigit():
            _, _, rest = line.partition(":")
            line = rest.strip()
        obj = json.loads(line)
        result.append(obj)
    return result


def _extract_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize an MC inbox row to our import shape."""
    ts = row.get("ts", "")
    from_seat = row.get("from", "unknown")
    project = row.get("project", "unknown")
    subject = row.get("subject", "")
    body = row.get("body", "")
    read_flag = row.get("read", False)

    # Generate deterministic message UUID
    dedup_key = f"{ts}:{from_seat}:{project}:{subject}"
    message_id = uuid5(_INBOX_NAMESPACE, dedup_key)

    return {
        "message_id": str(message_id),
        "ts": ts,
        "from": from_seat,
        "project": project,
        "subject": subject,
        "body": body,
        "read": read_flag,
        "content_sha256": hashlib.sha256(
            json.dumps({"subject": subject, "body": body}, sort_keys=True).encode()
        ).hexdigest(),
    }


def _read_stable_regular(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read a regular file, returning bytes and identity metadata."""
    st = path.stat()
    return path.read_bytes(), {
        "path": str(path.resolve()),
        "size": st.st_size,
        "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
    }


# ---- Analysis / dry run ----


def analyze_inbox_import(
    ledger_path: Path,
    *,
    seat_map_path: Path | None = None,
    project_key: str = "ctower",
    signer: ArtifactSigner | None = None,
) -> dict[str, Any]:
    """Read-only analysis: derive manifest without writing target state."""
    if not ledger_path.exists():
        raise FileNotFoundError(ledger_path)
    source_bytes, source_identity = read_stable_source(ledger_path)
    ledger_digest = sha256_digest(source_bytes)
    physical = _parse_inbox_jsonl(ledger_path)

    rows = [_extract_fields(r) for r in physical]

    source_count = len(rows)
    source_sha256 = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    # Load seat map if provided
    seat_map = _load_seat_map(seat_map_path)

    # Build batches
    batches: list[dict[str, Any]] = []
    for i in range(0, source_count, _BATCH_SIZE):
        batch_rows = rows[i : i + _BATCH_SIZE]
        batch_ids = [r["message_id"] for r in batch_rows]
        batch_index = i // _BATCH_SIZE
        batch_digest = sha256_digest(json.dumps(batch_rows, sort_keys=True).encode())
        batches.append(
            {
                "batch_index": batch_index,
                "batch_digest": f"sha256:{batch_digest}",
                "source_count": len(batch_rows),
                "cumulative_count": min(i + _BATCH_SIZE, source_count),
                "sample_ids": batch_ids[:3],
            }
        )

    # Build the manifest
    manifest: dict[str, Any] = {
        "schema": _SCHEMA,
        "ledger_sha256": f"sha256:{source_sha256}",
        "source_identity": source_identity,
        "project_key": project_key,
        "counts": {
            "physical_rows": source_count,
            "logical_messages": source_count,
        },
        "maximum_message_number": source_count,
        "batches": batches,
    }

    # Count unknown seats
    unknown_seats = set()
    for row in rows:
        if row["from"] not in seat_map:
            unknown_seats.add(row["from"])

    import_rows = _estate_rows(rows, ledger_path, seat_map)
    estate_manifest = build_estate_manifest(
        tier="inbox_history",
        source_identity=source_identity,
        rows=import_rows,
        seat_mapping_digest=_mapping_digest(seat_map_path),
        signer=signer,
    )

    # Sign if a signer is provided
    if signer is not None:
        manifest = signer.seal(manifest, "manifest_digest")

    return {
        "schema": "ctower.inbox-import-dry-run/v1",
        "mode": "DRY-RUN" if signer is None else "SIGNED",
        "eligible": source_count > 0,
        "ledger_digest": f"sha256:{ledger_digest}",
        "row_count": source_count,
        "batch_count": len(batches),
        "unknown_from_seats": sorted(unknown_seats),
        "unknown_seat_count": len(unknown_seats),
        "project_key": project_key,
        "writes_attempted": 0,
        "manifest": manifest,
        "estate_manifest": estate_manifest,
        "estate_rows": import_rows,
    }


def _estate_rows(
    rows: list[dict[str, Any]], ledger_path: Path, seat_map: dict[str, str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        source_seat = str(row["from"])
        target = seat_map.get(source_seat)
        result.append(
            {
                "_disposition": "mapped" if target is not None else "source_only",
                "content_sha256": f"sha256:{row['content_sha256']}",
                "source_ref": f"{ledger_path.name}#{index}",
                "source_seat": source_seat,
                "target_seat_key": target,
            }
        )
    return result


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


# ---- Execution ----


def execute_inbox_import(
    client: httpx.Client,
    *,
    ledger_path: Path,
    manifest_path: Path,
    evidence_dir: Path,
    signer: ArtifactSigner,
    base_url: str,
) -> dict[str, Any]:
    """Execute the inbox import via authenticated inbox send commands."""
    manifest = _signed_artifact(manifest_path, signer, "manifest_digest")
    _ = manifest  # validate shape via signature check
    physical = _parse_inbox_jsonl(ledger_path)
    rows = [_extract_fields(r) for r in physical]

    batches = manifest.get("batches", [])
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    import_rows = [_request_row(row, index) for index, row in enumerate(rows, 1)]
    response = client.post(
        f"{base_url}/v1/migrations/estate/inbox",
        json={"manifest": manifest, "rows": import_rows},
        timeout=60,
    )
    response.raise_for_status()
    result = cast(dict[str, Any], response.json())
    parity = result.get("parity")
    if isinstance(parity, dict):
        (evidence_dir / "parity.json").write_bytes(rfc8785.dumps(parity))
    imported = int(result.get("imported_count", len(rows)))
    return {
        "schema": "ctower.inbox-import-transcript/v1",
        "phase": "completed",
        "source_count": len(rows),
        "imported_count": imported,
        "batch_count": len(batches),
        "writes_attempted": imported + len(batches),
        "evidence_dir": str(evidence_dir),
        "parity": parity,
    }


def _request_row(row: dict[str, Any], line_number: int) -> dict[str, Any]:
    recipient = row.get("to") or row.get("recipient") or "operator"
    return {
        "message_id": row["message_id"],
        "source_ref": f"inbox.jsonl#{line_number}",
        "source_sender": row["from"],
        "source_recipient": recipient,
        "sent_at": row["ts"],
        "subject": row["subject"],
        "body": row["body"],
        "read_state": "read" if row["read"] else "delivered",
    }


# ---- CLI ----


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
            args.manifest_output.write_bytes(rfc8785.dumps(report["estate_manifest"]))
        return 0 if report["eligible"] else 3

    if not args.base_url:
        print("--base-url required for non-dry-run mode", file=__import__("sys").stderr)
        return 1
    if signer is None:
        print("signing args required for non-dry-run mode", file=__import__("sys").stderr)
        return 1

    with httpx.Client() as client:
        result = execute_inbox_import(
            client,
            ledger_path=args.ledger,
            manifest_path=args.manifest_output or Path("/dev/null"),
            evidence_dir=args.evidence,
            signer=signer,
            base_url=args.base_url,
        )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


_HTTP_CONFLICT = 409


def _signer(args: argparse.Namespace) -> ArtifactSigner | None:
    keys = (args.signing_key_map, args.signing_key_ref, args.signing_key_version)
    if all(v is None for v in keys):
        return None
    if any(v is None for v in keys):
        raise ValueError("signing arguments must be supplied together")
    return ArtifactSigner.from_reference_map(
        args.signing_key_map,
        args.signing_key_ref,
        key_version=args.signing_key_version,
    )


def _signed_artifact(path: Path, _signer: ArtifactSigner, digest_field: str) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("manifest must be a JSON object")
    _signer.verifier().verify(cast(dict[str, Any], raw), digest_field)
    return cast(dict[str, Any], raw)


if __name__ == "__main__":
    raise SystemExit(main())
