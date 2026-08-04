"""CI renders record-unavailable as neutral; every other refusal still renders FAILURE."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.landing_boundary import (
    ChangeIdentity,
    RecordSnapshot,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
    refused_report,
)
from tools.landing_boundary.ci_conclusion import (
    check_run_payload,
    conclusion_for,
    main,
    summary_for,
)

from . import support

__all__: tuple[str, ...] = ()

_USAGE_EXIT = 2
_ARGUMENTS = (
    "--repository",
    "simjak/ctower",
    "--pull-request",
    "199",
    "--head-revision",
    "4f" * 20,
)
_CHANGE = ChangeIdentity(
    repository="simjak/ctower", pull_request_reference="199", head_revision="4f" * 20
)
_POLICY = load_verdict_tier_policy()


def _record(tmp_path: Path, answer: dict[str, Any]) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(answer, indent=2), encoding="utf-8")
    return path


def _run(tmp_path: Path, record: Path | None, *extra: str) -> tuple[int, dict[str, Any]]:
    output = tmp_path / "check-run.json"
    arguments = (
        *_ARGUMENTS,
        "--record",
        "" if record is None else str(record),
        "--name",
        "landing boundary (record-backed)",
        "--output",
        str(output),
        *extra,
    )
    status = main(arguments)
    return status, json.loads(output.read_text(encoding="utf-8"))


# A1 -- the only refusal in CI today: no record answer was ever supplied.
def test_a_record_unavailable_refusal_renders_neutral_not_failure() -> None:
    report = refused_report(_CHANGE, "record-unavailable", "no record answer was supplied")

    assert conclusion_for(report) == "neutral"


def test_a_record_unavailable_refusal_still_names_the_refusal_in_the_summary() -> None:
    report = refused_report(_CHANGE, "record-unavailable", "no record answer was supplied")

    summary = summary_for(report, conclusion_for(report))

    assert "refused: record-unavailable" in summary
    assert "observe mode" in summary


# A2 -- a record answer that itself refuses must still render red.
def test_a_genuine_documentation_refusal_still_renders_failure() -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unfilled"
    )
    snapshot_report = evaluate_landing_boundary(_snapshot(answer), _CHANGE, _POLICY)

    assert conclusion_for(snapshot_report) == "failure"
    assert "missing-documentation-evidence" in summary_for(
        snapshot_report, conclusion_for(snapshot_report)
    )


def test_a_compliant_change_renders_success() -> None:
    snapshot_report = evaluate_landing_boundary(
        _snapshot(support.record_answer()), _CHANGE, _POLICY
    )

    assert conclusion_for(snapshot_report) == "success"


def test_a_malformed_record_answer_is_not_the_observe_mode_case() -> None:
    # A record answer that IS present but unreadable is a different refusal name than
    # `record-unavailable`, so it stays FAILURE -- this task widens no other case.
    report = refused_report(_CHANGE, "record-payload-invalid", "unreadable record snapshot")

    assert conclusion_for(report) == "failure"


def test_the_check_run_payload_names_the_canonical_required_check() -> None:
    report = refused_report(_CHANGE, "record-unavailable", "no record answer was supplied")

    payload = check_run_payload(report, name="landing boundary (record-backed)", head_sha="4f" * 20)

    assert payload.name == "landing boundary (record-backed)"
    assert payload.status == "completed"
    assert payload.conclusion == "neutral"
    assert "refused: record-unavailable" in payload.output.summary


# CLI end-to-end: both branches, proven through the same entry point CI invokes.
def test_cli_no_record_answer_writes_a_neutral_check_run_payload(tmp_path: Path) -> None:
    status, payload = _run(tmp_path, None)

    assert status == 0
    assert payload["conclusion"] == "neutral"
    assert "refused: record-unavailable" in payload["output"]["summary"]


def test_cli_a_genuine_refusal_writes_a_failure_check_run_payload(tmp_path: Path) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.REVIEW_STAGE, "round-manifest", state="unfilled"
    )

    status, payload = _run(tmp_path, _record(tmp_path, answer))

    assert status == 0
    assert payload["conclusion"] == "failure"
    assert "refused: missing-risk-derived-review-evidence" in payload["output"]["summary"]


def test_cli_a_compliant_change_writes_a_success_check_run_payload(tmp_path: Path) -> None:
    status, payload = _run(tmp_path, _record(tmp_path, support.record_answer()))

    assert status == 0
    assert payload["conclusion"] == "success"


def test_cli_a_malformed_record_answer_writes_a_failure_check_run_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "record.json"
    path.write_text("{", encoding="utf-8")

    status, payload = _run(tmp_path, path)

    assert status == 0
    assert payload["conclusion"] == "failure"
    assert "refused: record-payload-invalid" in payload["output"]["summary"]


def test_cli_a_malformed_change_identity_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = main(
        (
            "--repository",
            "not-a-repository",
            "--pull-request",
            "199",
            "--head-revision",
            "4f" * 20,
            "--record",
            "",
            "--name",
            "landing boundary (record-backed)",
            "--output",
            str(tmp_path / "check-run.json"),
        )
    )

    assert status == _USAGE_EXIT
    assert "landing boundary ci-conclusion:" in capsys.readouterr().err


def test_cli_an_unreadable_tier_policy_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = main(
        (
            *_ARGUMENTS,
            "--record",
            "",
            "--policy",
            str(tmp_path / "absent.toml"),
            "--name",
            "landing boundary (record-backed)",
            "--output",
            str(tmp_path / "check-run.json"),
        )
    )

    assert status == _USAGE_EXIT
    assert "landing boundary ci-conclusion:" in capsys.readouterr().err


def _snapshot(answer: dict[str, Any]) -> RecordSnapshot:
    return RecordSnapshot.model_validate_json(json.dumps(answer))


@pytest.mark.parametrize(
    ("refusal", "expected"),
    [
        ("record-unavailable", "neutral"),
        ("record-answers-a-different-change", "failure"),
        ("record-payload-invalid", "failure"),
        ("change-not-bound-to-ticket", "failure"),
        ("candidate-digest-unresolved", "failure"),
        ("pinned-workflow-unresolved", "failure"),
        ("landing-boundary-undeclared", "failure"),
    ],
)
def test_every_pre_fact_refusal_renders_the_expected_conclusion(
    refusal: str, expected: str
) -> None:
    report = refused_report(_CHANGE, refusal, "detail")

    assert conclusion_for(report) == expected
