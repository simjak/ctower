"""The check as CI runs it: exit status, named refusals, and no authoritative write."""

from __future__ import annotations

import json
from contextlib import chdir
from pathlib import Path
from typing import Any

import pytest

from tools.landing_boundary.cli import main

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


def _record(tmp_path: Path, answer: dict[str, Any]) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(answer, indent=2), encoding="utf-8")
    return path


def _run(record: Path | None, *extra: str) -> int:
    arguments = (*_ARGUMENTS, "--record", "" if record is None else str(record), *extra)
    return main(arguments)


def test_a_compliant_change_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status = _run(_record(tmp_path, support.record_answer()))

    assert status == 0
    assert "landing boundary: PASS" in capsys.readouterr().out


def test_a_change_without_documentation_evidence_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unfilled"
    )

    status = _run(_record(tmp_path, answer))
    captured = capsys.readouterr().out

    assert status == 1
    assert "refused: missing-documentation-evidence" in captured
    assert "revision: slot-unfilled" in captured


def test_a_change_without_review_evidence_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.REVIEW_STAGE, "round-manifest", state="unfilled"
    )

    status = _run(_record(tmp_path, answer))

    assert status == 1
    assert "refused: missing-risk-derived-review-evidence" in capsys.readouterr().out


def test_an_unknown_fact_is_reported_as_a_failure_not_a_caveat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unknown"
    )

    status = _run(_record(tmp_path, answer))
    captured = capsys.readouterr().out

    assert status == 1
    assert "STATE_UNKNOWN" in captured
    assert "refused: missing-documentation-evidence" in captured


def test_no_record_answer_refuses_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = _run(None)
    captured = capsys.readouterr().out

    assert status == 1
    assert "refused: record-unavailable" in captured


def test_a_malformed_record_answer_refuses_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "record.json"
    path.write_text("{", encoding="utf-8")

    status = _run(path)
    captured = capsys.readouterr().out

    assert status == 1
    assert "refused: record-payload-invalid" in captured


def test_a_json_verdict_is_deterministic_and_typed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unfilled"
    )

    status = _run(_record(tmp_path, answer), "--json")
    document = json.loads(capsys.readouterr().out)

    assert status == 1
    assert document["schema"] == "ctower.landing-boundary-report/v1"
    assert document["verdict"] == "refused"
    assert document["refusals"] == ["missing-documentation-evidence"]


def test_a_malformed_change_identity_is_a_usage_error(
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
            str(_record(tmp_path, support.record_answer())),
        )
    )

    assert status == _USAGE_EXIT
    assert "landing boundary:" in capsys.readouterr().err


def test_an_unreadable_tier_policy_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = _run(
        _record(tmp_path, support.record_answer()), "--policy", str(tmp_path / "absent.toml")
    )

    assert status == _USAGE_EXIT
    assert "landing boundary:" in capsys.readouterr().err


@pytest.mark.parametrize("state", ["filled", "unfilled", "unknown"])
def test_every_verdict_leaves_the_record_answer_and_the_tree_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state=state
    )
    record = _record(tmp_path, answer)
    before = record.read_bytes()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with chdir(workspace):
        _run(record)
    capsys.readouterr()

    assert record.read_bytes() == before
    assert list(workspace.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["record.json", "workspace"]
