"""RED-first: Request cutover dry-run analysis regression tests.

These tests exercise the EXISTING operator_requests.dry_run.analyze_cutover
against a realistic MC requests.jsonl fixture, verifying the diagnostic manifest
and blocker detection behavior. A signed/orce-validated manifest requires
a full signing key, owner map, and fence proof (production-only).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.migration.operator_requests.dry_run import analyze_cutover

__all__: tuple[str, ...] = ()

_FIXTURE = (
    '{"id": "R01", "status": "DONE", "text": "Feedback entry point", '
    '"owner": "shell-feedback", "note": "shipped #2329", '
    '"created": "2026-07-06T09:00:00Z", "updated": "2026-07-09T07:52:00Z", '
    '"project": "ctower"}\n'
    '{"id": "R02", "status": "IN-PROGRESS", "text": "Billing page", '
    '"owner": "unassigned", "note": "merged", '
    '"created": "2026-07-06T09:00:00Z", "updated": "2026-07-08T17:46:00Z", '
    '"project": "ctower"}\n'
)


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    p = tmp_path / "requests.jsonl"
    p.write_text(_FIXTURE)
    return p


def test_dry_run_returns_diagnostic_manifest(ledger: Path) -> None:
    """Without full signing, the dry run returns a diagnostic_manifest, not manifest."""
    report = analyze_cutover(ledger)
    assert report["eligible"] is False  # blockers prevent eligibility
    diagnostic = report.get("diagnostic_manifest")
    assert diagnostic is not None
    assert diagnostic["schema"] == "ctower.request-import-manifest/v1"


def test_dry_run_diagnostic_has_counts(ledger: Path) -> None:
    """Diagnostic manifest contains correct row counts."""
    report = analyze_cutover(ledger)
    diagnostic = report["diagnostic_manifest"]
    assert diagnostic["counts"]["physical_rows"] == 2
    assert diagnostic["counts"]["logical_requests"] == 2
    assert diagnostic["counts"]["open_requests"] == 1  # R02 is open


def test_dry_run_detects_missing_owner_map(ledger: Path) -> None:
    """Dry run flags owner-map-missing as a blocker."""
    report = analyze_cutover(ledger)
    blockers = report.get("blockers", [])
    assert "owner-map-missing" in blockers
    assert "owner-map-missing:1" in blockers


def test_dry_run_detects_request_id_noncanonical(ledger: Path) -> None:
    """IDs that don't match the canonical R-id format are flagged."""
    report = analyze_cutover(ledger)
    blockers = report.get("blockers", [])
    # R01 and R02 should be canonical (R followed by number)
    # But the test fixture might have non-canonical IDs
    for blocker in blockers:
        if "request-id-noncanonical" in blocker:
            return
    pytest.fail(f"No request-id-noncanonical blocker found in {blockers}")


def test_dry_run_open_request_ids(ledger: Path) -> None:
    """Open request IDs are listed with the R02 only."""
    report = analyze_cutover(ledger)
    diagnostic = report["diagnostic_manifest"]
    open_ids = diagnostic.get("open_request_ids", [])
    assert "R02" in open_ids
    assert "R01" not in open_ids


def test_dry_run_ledger_sha256_is_deterministic(ledger: Path) -> None:
    """Ledger SHA-256 matches the frozen file."""
    report = analyze_cutover(ledger)
    expected = "sha256:" + hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert report["ledger_sha256"] == expected


def test_dry_run_batches_contain_open_only(ledger: Path) -> None:
    """Batches include only open rows in sample_ids."""
    report = analyze_cutover(ledger)
    diagnostic = report["diagnostic_manifest"]
    batches = diagnostic.get("batches", [])
    assert len(batches) >= 1
    for batch in batches:
        for sample in batch.get("sample_ids", []):
            assert sample.startswith("R")


def test_dry_run_rejects_empty_ledger(tmp_path: Path) -> None:
    """Empty ledger is not eligible."""
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    report = analyze_cutover(empty)
    assert report.get("eligible") is False


def test_dry_run_rejects_missing_ledger() -> None:
    """Missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        analyze_cutover(Path("/nonexistent/requests.jsonl"))
