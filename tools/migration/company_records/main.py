"""Company records import for escapes/accountability data (R3000 surface 8).

This is the sanctioned safe-degraded candidate. It reads frozen MC
state/escapes.jsonl and creates company record entries as knowledge
documents under a dedicated project scope.

If the window compresses, this tool becomes the working shim + ticket.

Usage:
  python -m tools.migration.company_records.main \\
    --escapes /path/to/escapes.jsonl \\
    --project ctower \\
    [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import uuid as uuid_mod
from pathlib import Path
from typing import Any

__all__ = ["analyze_escapes_import"]

_ESCAPE_NAMESPACE = uuid_mod.UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")


def _parse_escapes(path: Path) -> list[dict[str, Any]]:
    """Parse MC escapes.jsonl."""
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        record = json.loads(line)
        record_id = record.get("date", "") + ":" + record.get("defect", "")[:80]
        record["record_id"] = str(uuid_mod.uuid5(_ESCAPE_NAMESPACE, record_id))
        records.append(record)
    return records


def analyze_escapes_import(
    escapes_path: Path,
    *,
    project_key: str = "ctower",
) -> dict[str, Any]:
    """Read-only analysis of for the escapes import."""
    if not escapes_path.is_file():
        return {
            "schema": "ctower.company-records-import-dry-run/v1",
            "mode": "DRY-RUN",
            "eligible": False,
            "error": f"file not found: {escapes_path}",
            "writes_attempted": 0,
        }

    records = _parse_escapes(escapes_path)
    source_count = len(records)

    return {
        "schema": "ctower.company-records-import-dry-run/v1",
        "mode": "DRY-RUN",
        "eligible": source_count > 0,
        "escapes_count": source_count,
        "project_key": project_key,
        "writes_attempted": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC escapes/company-records import")
    parser.add_argument("--escapes", required=True, type=Path)
    parser.add_argument("--project", default="ctower")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = analyze_escapes_import(args.escapes, project_key=args.project)

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report.get("eligible", False) else 3


if __name__ == "__main__":
    raise SystemExit(main())
