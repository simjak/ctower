"""Fail-closed one-way Request ledger cutover planning and reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

from tools.migration.operator_requests.dry_run import analyze_cutover

__all__: tuple[str, ...] = ()

_FIXTURE_HIGH_WATER = 12
_FIXTURE_OPEN_COUNT = 2


def test_signed_denominator_batches_counts_and_samples_are_deterministic(tmp_path: Path) -> None:
    ledger, owners, fence = _eligible_fixture(tmp_path)

    first = analyze_cutover(ledger, owner_map_path=owners, fence_proof_path=fence)
    second = analyze_cutover(ledger, owner_map_path=owners, fence_proof_path=fence)

    assert first["counts"] == {
        "physical_rows": 4,
        "logical_requests": 3,
        "open_requests": 2,
        "open_by_project": {"ctower": 1, "manibo": 1},
    }
    assert first["maximum_request_number"] == _FIXTURE_HIGH_WATER
    assert first["batches"][0]["source_count"] == _FIXTURE_OPEN_COUNT
    assert first["batches"][0]["sample_count"] == _FIXTURE_OPEN_COUNT
    assert first["batches"][0]["sample"] == second["batches"][0]["sample"]
    assert first["manifest_digest"] == second["manifest_digest"]
    assert first["projections"]["R10"]["triage"] == "ACCEPTED"
    assert first["projections"]["R10"]["blocker"] is True
    assert first["projections"]["R11"]["triage"] == "ACCEPTED"
    assert first["projections"]["R11"]["state"] == "TRIAGED"
    assert first["eligible"] is False
    assert first["blockers"] == ["fence-ledger-digest-unbound", "manifest-unsigned"]


def _eligible_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    ledger = tmp_path / "requests.jsonl"
    rows = [
        _row("R10", "NEW", "ctower", "ctower-commander", "first"),
        _row("R11", "TRIAGED", "manibo", "manibo-commander", "second"),
        _row("R12", "DONE", "ctower", "ctower-commander", "closed"),
        {
            **_row("R10", "BLOCKED", "ctower", "ctower-commander", "first"),
            "note": "waiting on an explicit decision",
            "history": [
                {"at": "2026-08-10 01:00", "actor": "operator", "event": "created", "to": "NEW"},
                {
                    "at": "2026-08-10 02:00",
                    "actor": "operator",
                    "event": "status_set",
                    "from": "NEW",
                    "to": "BLOCKED",
                },
            ],
            "updated": "2026-08-10 02:00",
        },
    ]
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    ledger.chmod(0o444)
    owners = tmp_path / "owners.json"
    owners.write_text(
        json.dumps(
            {
                "schema": "ctower.request-owner-map/v1",
                "reviewed_at": "2026-08-10T02:30:00Z",
                "reviewed_by": "operator",
                "mappings": [
                    {
                        "project_key": "ctower",
                        "source_owner": "ctower-commander",
                        "principal_id": "018f0d5e-7b9a-7c01-8000-000000000010",
                    },
                    {
                        "project_key": "manibo",
                        "source_owner": "manibo-commander",
                        "principal_id": "018f0d5e-7b9a-7c01-8000-000000000011",
                    },
                ],
                "request_reviews": [
                    {"id": "R10", "priority": "P1"},
                    {"id": "R11", "priority": "P2"},
                ],
            }
        ),
        encoding="utf-8",
    )
    fence = tmp_path / "fence.json"
    fence.write_text(
        json.dumps(
            {
                "schema": "ctower.request-source-fence/v1",
                "ledger_sha256": "AUTO",
                "mutation_entrypoints_removed": True,
                "writer_refuses": True,
            }
        ),
        encoding="utf-8",
    )
    return ledger, owners, fence


def test_missing_project_owner_mapping_and_source_writability_block_cutover(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "requests.jsonl"
    ledger.write_text(
        json.dumps(_row("R20", "NEW", None, "unknown-owner", "unbound")) + "\n",
        encoding="utf-8",
    )

    report = analyze_cutover(ledger)

    assert report["eligible"] is False
    assert report["counts"]["open_requests"] == 1
    assert report["blocker_counts"]["open-project-unbound"] == 1
    assert report["blocker_counts"]["owner-map-missing"] == 1
    assert "source-ledger-writable" in report["blockers"]
    assert "source-fence-proof-missing" in report["blockers"]


def _row(
    request_id: str,
    status: str,
    project: str | None,
    owner: str,
    text: str,
) -> dict[str, object]:
    return {
        "id": request_id,
        "record_type": "request",
        "status": status,
        "text": text,
        "owner": owner,
        "note": "",
        "project": project,
        "created": "2026-08-10 01:00",
        "updated": "2026-08-10 01:00",
        "active": status != "DONE",
        "relationships": [],
        "history": [
            {"at": "2026-08-10 01:00", "actor": "operator", "event": "created", "to": "NEW"}
        ],
        "refines": [],
    }
