"""RED-first: company records (escapes) import tool tests."""

from __future__ import annotations

from pathlib import Path

from tools.migration.company_records.main import _parse_escapes, analyze_escapes_import

__all__: tuple[str, ...] = ()

_FIXTURE = (
    '{"date": "2026-07-27", "defect": "tenant trunk-create shipped DARK on prod", '
    '"signed_by": "release-manager+qa+commander", "seat": "commander", '
    '"should_have_caught": "headline use-proof", '
    '"gate_hardened": "cadence C.5b headline use-proof + dark-flag audit", '
    '"found_by": "operator"}\n'
    '{"date": "2026-07-27", "defect": "warm-transfer API 503", '
    '"signed_by": "engineer+devops", "seat": "devops", '
    '"should_have_caught": "provisioning of the three *_REF settings", '
    '"gate_hardened": "C.5d no-prod-feature-without-e2e", '
    '"found_by": "operator"}\n'
)


def test_parse_escapes_parses_jsonl(tmp_path: Path) -> None:
    """Parse escapes.jsonl lines into records with record_id."""
    path = tmp_path / "escapes.jsonl"
    path.write_text(_FIXTURE)
    records = _parse_escapes(path)
    assert len(records) == 2
    assert records[0]["date"] == "2026-07-27"
    assert records[0]["defect"].startswith("tenant trunk-create")
    assert "record_id" in records[0]


def test_parse_escapes_deterministic_id(tmp_path: Path) -> None:
    """Same input → same record_id (idempotency)."""
    path = tmp_path / "escapes.jsonl"
    path.write_text(_FIXTURE)
    records_a = _parse_escapes(path)
    records_b = _parse_escapes(path)
    assert records_a[0]["record_id"] == records_b[0]["record_id"]


def test_parse_escapes_empty_file(tmp_path: Path) -> None:
    """Empty file yields zero records."""
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    assert _parse_escapes(path) == []


def test_analyze_dry_run_reports_count(tmp_path: Path) -> None:
    """Dry-run returns correct escapes count."""
    path = tmp_path / "escapes.jsonl"
    path.write_text(_FIXTURE)
    report = analyze_escapes_import(path, project_key="ctower")
    assert report["eligible"] is True
    assert report["escapes_count"] == 2


def test_analyze_dry_run_missing_file() -> None:
    """Missing escapes file returns structured error."""
    report = analyze_escapes_import(Path("/nonexistent/escapes.jsonl"), project_key="ctower")
    assert report["eligible"] is False
    assert "error" in report


def test_analyze_dry_run_empty_file(tmp_path: Path) -> None:
    """Empty file returns ineligible (0 records)."""
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    report = analyze_escapes_import(path, project_key="ctower")
    assert report["eligible"] is False
    assert report["escapes_count"] == 0
