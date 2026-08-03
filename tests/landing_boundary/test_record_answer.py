"""No answer, a different answer, or a smuggled bypass is a refusal, never a pass."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.landing_boundary import (
    ChangeIdentity,
    LandingBoundaryError,
    LandingBoundaryReport,
    RecordSnapshot,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
    read_record_snapshot,
)

from . import support

__all__: tuple[str, ...] = ()

_BYPASS_FIELDS = {
    "label": "documentation-exempt",
    "labels": ["ship-it"],
    "administrator_merge": True,
    "admin_override": True,
    "rerun_count": 3,
    "follow_up_ticket": "CT-9999",
    "repository_quality_gate": "green",
    "reviewer_assertion": "docs exist",
    "operator_waiver": {"granted_by": "operator"},
    "waived": True,
}


def _report(answer: dict[str, Any]) -> LandingBoundaryReport:
    return evaluate_landing_boundary(
        RecordSnapshot.model_validate_json(json.dumps(answer)),
        ChangeIdentity(**support.CHANGE),
        load_verdict_tier_policy(),
    )


def test_an_explicitly_unavailable_record_refuses() -> None:
    answer = support.record_answer()
    answer["availability"] = "unavailable"

    assert _report(answer).refusals == ("record-unavailable",)


def test_an_answer_for_a_different_head_revision_refuses() -> None:
    answer = support.record_answer()
    answer["change"]["head_revision"] = "ab" * 20

    assert _report(answer).refusals == ("record-answers-a-different-change",)


def test_an_answer_for_a_different_pull_request_refuses() -> None:
    answer = support.record_answer()
    answer["change"]["pull_request_reference"] = "1"

    assert _report(answer).refusals == ("record-answers-a-different-change",)


def test_a_change_the_record_binds_to_no_ticket_refuses() -> None:
    answer = support.record_answer()
    answer["binding"] = None

    assert _report(answer).refusals == ("change-not-bound-to-ticket",)


def test_a_head_revision_that_resolves_to_no_candidate_refuses() -> None:
    answer = support.record_answer()
    answer["binding"]["candidate_digest"] = None

    assert _report(answer).refusals == ("candidate-digest-unresolved",)


def test_a_ticket_with_no_pinned_workflow_refuses() -> None:
    answer = support.record_answer()
    answer["workflow"] = None
    report = _report(answer)

    assert report.refusals == ("pinned-workflow-unresolved",)
    assert report.facts == ()


def test_a_pinned_graph_that_does_not_parse_refuses() -> None:
    answer = support.record_answer()
    answer["workflow"]["graph"] = {"schema": "ctower.workflow/v1"}

    assert _report(answer).refusals == ("pinned-workflow-invalid",)


def test_a_pinned_graph_whose_digest_does_not_match_refuses() -> None:
    answer = support.record_answer()
    answer["workflow"]["graph_digest"] = "sha256:" + "0" * 64

    assert _report(answer).refusals == ("pinned-workflow-digest-mismatch",)


def test_a_checkpoint_that_never_declared_its_landing_boundary_refuses() -> None:
    answer = support.record_answer(landing_boundary_stage=None)

    assert _report(answer).refusals == ("landing-boundary-undeclared",)


def test_a_landing_boundary_the_graph_cannot_reach_refuses() -> None:
    payload = support.graph_payload(("intake", "think"))
    payload["stages"] = [*payload["stages"], {"key": "orphan", "activity_class": "work"}]
    answer = support.record_answer(
        stage_keys=("intake", "think"), landing_boundary_stage="orphan", graph=payload
    )

    assert _report(answer).refusals == ("landing-boundary-unreachable",)


@pytest.mark.parametrize(("field", "value"), sorted(_BYPASS_FIELDS.items()))
def test_no_bypass_can_be_expressed_at_the_document(
    tmp_path: Path, field: str, value: object
) -> None:
    answer = support.record_answer()
    answer[field] = value

    _assert_refused_payload(tmp_path, answer, field)


@pytest.mark.parametrize(("field", "value"), sorted(_BYPASS_FIELDS.items()))
def test_no_bypass_can_be_expressed_on_a_stage(tmp_path: Path, field: str, value: object) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unfilled"
    )
    for stage in answer["stages"]:
        if stage["stage_key"] == support.DOCS_STAGE:
            stage[field] = value

    _assert_refused_payload(tmp_path, answer, field)


@pytest.mark.parametrize(("field", "value"), sorted(_BYPASS_FIELDS.items()))
def test_no_bypass_can_be_expressed_on_a_slot(tmp_path: Path, field: str, value: object) -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, "revision", state="unfilled", **{field: value}
    )

    _assert_refused_payload(tmp_path, answer, field)


def _assert_refused_payload(tmp_path: Path, answer: dict[str, Any], field: str) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(answer), encoding="utf-8")

    with pytest.raises(LandingBoundaryError, match="typed contract"):
        read_record_snapshot(path)
    assert field in _BYPASS_FIELDS


def test_a_repeated_stage_key_is_refused_rather_than_resolved(tmp_path: Path) -> None:
    answer = support.record_answer()
    answer["stages"] = [*answer["stages"], answer["stages"][0]]
    path = tmp_path / "record.json"
    path.write_text(json.dumps(answer), encoding="utf-8")

    with pytest.raises(LandingBoundaryError, match="typed contract"):
        read_record_snapshot(path)


def test_a_repeated_slot_key_is_refused_rather_than_resolved(tmp_path: Path) -> None:
    answer = support.record_answer()
    for stage in answer["stages"]:
        if stage["stage_key"] == support.DOCS_STAGE:
            stage["required_slots"] = [stage["required_slots"][0], stage["required_slots"][0]]
    path = tmp_path / "record.json"
    path.write_text(json.dumps(answer), encoding="utf-8")

    with pytest.raises(LandingBoundaryError, match="typed contract"):
        read_record_snapshot(path)


def test_an_unreadable_record_answer_is_not_an_answer(tmp_path: Path) -> None:
    with pytest.raises(LandingBoundaryError, match="unreadable"):
        read_record_snapshot(tmp_path / "absent.json")


def test_a_compliant_answer_round_trips_through_the_reader(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(support.record_answer()), encoding="utf-8")

    snapshot = read_record_snapshot(path)

    assert snapshot.availability == "available"
    assert snapshot.binding is not None
    assert snapshot.binding.candidate_digest == support.CANDIDATE
