"""RED-first: company records (escapes) import tool tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ctower_kernel.record._estate_import_sql import CompanyRecordAppend, _same_record
from tools.migration.company_records.main import (
    _parse_escapes,
    analyze_escapes_import,
    execute_escapes_import,
)

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


class _Response:
    status_code = 201

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"imported_count": 1, "parity": {"schema": "ctower.estate-import-parity/v1"}}


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: Mapping[str, str],
        timeout: float,
    ) -> _Response:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _Response()


def test_execute_posts_bounded_company_estate_batch_with_idempotency_key(tmp_path: Path) -> None:
    path = tmp_path / "escapes.jsonl"
    path.write_text(_FIXTURE)
    client = _RecordingClient()

    result = execute_escapes_import(
        client,
        escapes_path=path,
        manifest={
            "manifest_digest": "sha256:" + "1" * 64,
            "batches": [{"batch_index": 0, "source_count": 2}],
        },
        base_url="https://ctower.test",
        evidence_dir=tmp_path / "evidence",
    )

    assert result["source_count"] == 2
    assert result["imported_count"] == 1
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://ctower.test/v1/migrations/estate/company-records"
    payload = call["json"]
    assert isinstance(payload, dict)
    assert payload["batch_index"] == 0
    headers = call["headers"]
    assert isinstance(headers, dict)
    assert headers["Idempotency-Key"]
    assert call["timeout"] == 60


def test_company_record_replay_ignores_new_import_timestamp() -> None:
    command = CompanyRecordAppend(
        uuid4(),
        "escape",
        "escape:one",
        "2026-07-27",
        "commander",
        (("defect", "example"),),
        "state/escapes.jsonl#1",
        datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert (
        _same_record(
            {
                "occurred_on": "2026-07-27",
                "seat": "commander",
                "payload_sha256": bytes.fromhex("0" * 64),
                "source_ref": "state/escapes.jsonl#1",
                "imported_at": datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            },
            command,
            "0" * 64,
        )
        is True
    )
