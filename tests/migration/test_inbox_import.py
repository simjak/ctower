"""RED-first: inbox import tool analysis/parsing regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.migration.operator_inbox.main import (
    _extract_fields,
    _parse_inbox_jsonl,
    analyze_inbox_import,
)

__all__: tuple[str, ...] = ()

_FIXTURE = (
    b'1:{"ts": "2026-07-27T17:05:49Z", "from": "day-test", "severity": "info", '
    b'"project": "manibo", "subject": "day-namespace verification", '
    b'"body": "verified ok", "read": true}\n'
    b'2:{"ts": "2026-07-27T17:11:43Z", "from": "revert-test", "severity": "info", '
    b'"project": "ctower", "subject": "single-file ctower", '
    b'"body": "single file test", "read": false}\n'
)


def test_parse_jsonl_strips_line_numbers() -> None:
    """MC inbox.jsonl uses LINENUM:{...} format; tool must strip the prefix."""
    path = _write_fixture(_FIXTURE)
    rows = _parse_inbox_jsonl(path)
    assert len(rows) == 2
    assert rows[0]["from"] == "day-test"
    assert rows[1]["from"] == "revert-test"


def test_extract_fields_preserves_all_columns() -> None:
    """Every MC inbox column survives extraction with correct types."""
    row = _extract_fields(
        {
            "ts": "2026-07-27T17:05:49Z",
            "from": "day-test",
            "severity": "info",
            "project": "manibo",
            "subject": "day-namespace verification",
            "body": "verified ok",
            "read": True,
        }
    )
    assert row["ts"] == "2026-07-27T17:05:49Z"
    assert row["from"] == "day-test"
    assert row["project"] == "manibo"
    assert row["subject"] == "day-namespace verification"
    assert row["body"] == "verified ok"
    assert row["read"] is True
    assert isinstance(row["message_id"], str)
    assert len(row["message_id"]) == 36  # UUID


def test_extract_fields_deterministic_dedup_key() -> None:
    """Same input = same message_id (idempotency guarantee)."""
    row_a = _extract_fields(
        {"ts": "T1", "from": "seat-a", "project": "p", "subject": "s", "body": "b", "read": False}
    )
    row_b = _extract_fields(
        {"ts": "T1", "from": "seat-a", "project": "p", "subject": "s", "body": "b", "read": False}
    )
    assert row_a["message_id"] == row_b["message_id"]


def test_extract_fields_different_input_different_key() -> None:
    """Different (ts, from, project, subject) = different message_id."""
    row_a = _extract_fields(
        {"ts": "T1", "from": "seat-a", "project": "p", "subject": "s", "body": "b", "read": False}
    )
    row_b = _extract_fields(
        {"ts": "T2", "from": "seat-a", "project": "p", "subject": "s", "body": "b", "read": False}
    )
    assert row_a["message_id"] != row_b["message_id"]


def test_analyze_dry_run_rejects_without_ledger() -> None:
    """Dry-run without a ledger file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        analyze_inbox_import(Path("/nonexistent/inbox.jsonl"), project_key="ctower")


def test_analyze_dry_run_reports_counts() -> None:
    """Dry-run returns correct row and batch counts."""
    path = _write_fixture(_FIXTURE)
    report = analyze_inbox_import(path, project_key="ctower")
    assert report["row_count"] == 2
    assert report["batch_count"] == 1  # 2 rows, batch size 100
    assert report["project_key"] == "ctower"
    assert report["unknown_seat_count"] == 2


def test_analyze_dry_run_includes_manifest() -> None:
    """Dry-run produces a structured manifest dict."""
    path = _write_fixture(_FIXTURE)
    report = analyze_inbox_import(path, project_key="ctower")
    manifest = report.get("manifest")
    assert manifest is not None
    assert manifest["schema"] == "ctower.inbox-import-manifest/v1"
    assert manifest["project_key"] == "ctower"
    assert manifest["counts"]["physical_rows"] == 2


def test_analyze_dry_run_unknown_seats_empty() -> None:
    """Without seat map, from-seats are all unknown."""
    path = _write_fixture(_FIXTURE)
    report = analyze_inbox_import(path, project_key="ctower")
    assert set(report["unknown_from_seats"]) == {"day-test", "revert-test"}


def _write_fixture(content: bytes) -> Path:
    path = Path(f"/tmp/test_inbox_fixture_{hash(content)}.jsonl")
    path.write_bytes(content)
    return path
