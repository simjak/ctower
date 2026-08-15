"""RED-first: rulings import tool analysis/parsing regression tests."""

from __future__ import annotations

from pathlib import Path

from tools.migration.operator_rulings.main import (
    _parse_agreed_files,
    analyze_rulings_import,
)

__all__: tuple[str, ...] = ()


def test_parse_agreed_files_finds_md_files(tmp_path: Path) -> None:
    """Scans agreed-*.md files in the directory."""
    (tmp_path / "agreed-foo.md").write_text("# Foo Decision\n\nApproved.")
    (tmp_path / "agreed-bar.md").write_text("# Bar Decision\n\nRejected.")
    (tmp_path / "unrelated.txt").write_text("not a ruling")
    rulings = _parse_agreed_files(tmp_path)
    assert len(rulings) == 2


def test_parse_agreed_files_extracts_heading(tmp_path: Path) -> None:
    """First # heading becomes the ruling heading."""
    (tmp_path / "agreed-test.md").write_text("# My Heading\n\nBody text.\n")
    rulings = _parse_agreed_files(tmp_path)
    assert rulings[0]["heading"] == "My Heading"


def test_parse_agreed_files_empty_dir(tmp_path: Path) -> None:
    """An empty directory yields zero rulings."""
    rulings = _parse_agreed_files(tmp_path)
    assert len(rulings) == 0


def test_analyze_dry_run_reports_correct_count(tmp_path: Path) -> None:
    """Dry-run returns ruling count matching files found."""
    (tmp_path / "agreed-alpha.md").write_text("# Alpha\n\nContent A.\n")
    (tmp_path / "agreed-beta.md").write_text("# Beta\n\nContent B.\n")
    report = analyze_rulings_import(tmp_path, project_key="ctower")
    assert report["eligible"] is True
    assert report["ruling_count"] == 2


def test_analyze_dry_run_no_files(tmp_path: Path) -> None:
    """Empty board directory produces ineligible report."""
    report = analyze_rulings_import(tmp_path, project_key="ctower")
    assert report["eligible"] is False
    assert report["ruling_count"] == 0


def test_analyze_dry_run_nonexistent_dir() -> None:
    """Non-existent directory returns structured error."""
    report = analyze_rulings_import(Path("/nonexistent/board"), project_key="ctower")
    assert report["eligible"] is False
    assert "error" in report


def test_analyze_dry_run_produces_manifest(tmp_path: Path) -> None:
    """Dry-run includes a manifest with rulings array."""
    (tmp_path / "agreed-test.md").write_text("# Test\n\nBody.")
    report = analyze_rulings_import(tmp_path, project_key="ctower")
    manifest = report.get("manifest")
    assert manifest is not None
    assert manifest["schema"] == "ctower.ruling-import-manifest/v1"
    assert len(manifest["rulings"]) == 1
    assert manifest["rulings"][0]["filename"] == "agreed-test.md"
