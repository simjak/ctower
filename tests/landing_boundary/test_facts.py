"""One gate, two facts: each refusal fires by name, and a compliant change passes."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tools.landing_boundary import (
    ChangeIdentity,
    LandingBoundaryReport,
    RecordSnapshot,
    evaluate_landing_boundary,
    load_verdict_tier_policy,
)
from tools.landing_boundary.report import FactStatus, FindingReason, StageFact

from . import support

__all__: tuple[str, ...] = ()

_REVIEW_SLOT = "round-manifest"
_DOCS_SLOT = "revision"


def _report(answer: dict[str, Any]) -> LandingBoundaryReport:
    return evaluate_landing_boundary(
        RecordSnapshot.model_validate_json(json.dumps(answer)),
        ChangeIdentity(**support.CHANGE),
        load_verdict_tier_policy(),
    )


def _fact(report: LandingBoundaryReport, stage_key: str) -> StageFact:
    return next(fact for fact in report.facts if fact.stage_key == stage_key)


def _reasons(report: LandingBoundaryReport, stage_key: str) -> tuple[FindingReason, ...]:
    return tuple(finding.reason for finding in _fact(report, stage_key).findings)


def test_a_compliant_change_passes_every_fact() -> None:
    report = _report(support.record_answer())

    assert report.verdict == "pass"
    assert report.refusals == ()
    assert {fact.status for fact in report.facts} == {FactStatus.PASSING}


def test_missing_documentation_evidence_refuses_by_name() -> None:
    report = _report(
        support.replace_slot(
            support.record_answer(), support.DOCS_STAGE, _DOCS_SLOT, state="unfilled"
        )
    )

    assert report.verdict == "refused"
    assert report.refusals == ("missing-documentation-evidence",)
    assert _fact(report, support.DOCS_STAGE).status is FactStatus.FAIL
    assert _reasons(report, support.DOCS_STAGE) == (FindingReason.SLOT_UNFILLED,)


def test_missing_review_evidence_refuses_by_name() -> None:
    report = _report(
        support.replace_slot(
            support.record_answer(), support.REVIEW_STAGE, _REVIEW_SLOT, state="unfilled"
        )
    )

    assert report.verdict == "refused"
    assert report.refusals == ("missing-risk-derived-review-evidence",)
    assert _fact(report, support.REVIEW_STAGE).status is FactStatus.FAIL


def test_review_evidence_alone_does_not_carry_a_change_over_the_boundary() -> None:
    report = _report(
        support.replace_slot(
            support.record_answer(), support.DOCS_STAGE, _DOCS_SLOT, state="unfilled"
        )
    )

    assert _fact(report, support.REVIEW_STAGE).status is FactStatus.PASSING
    assert report.verdict == "refused"


def test_every_unmet_fact_is_named_alongside_the_others() -> None:
    answer = support.replace_slot(
        support.record_answer(), support.DOCS_STAGE, _DOCS_SLOT, state="unfilled"
    )
    report = _report(
        support.replace_slot(answer, support.REVIEW_STAGE, _REVIEW_SLOT, state="unfilled")
    )

    assert report.refusals == (
        "missing-risk-derived-review-evidence",
        "missing-documentation-evidence",
    )


@pytest.mark.parametrize(
    ("changes", "reason", "status"),
    [
        ({"state": "unknown"}, FindingReason.SLOT_STATE_UNKNOWN, FactStatus.STATE_UNKNOWN),
        ({"validity": "unknown"}, FindingReason.SLOT_VALIDITY_UNKNOWN, FactStatus.STATE_UNKNOWN),
        ({"validity": "invalidated"}, FindingReason.SLOT_NOT_CURRENT, FactStatus.FAIL),
        ({"validity": "expired"}, FindingReason.SLOT_NOT_CURRENT, FactStatus.FAIL),
        ({"validity": "revoked"}, FindingReason.SLOT_NOT_CURRENT, FactStatus.FAIL),
        (
            {"bound_candidate_digest": None},
            FindingReason.SLOT_CANDIDATE_UNBOUND,
            FactStatus.STATE_UNKNOWN,
        ),
        (
            {"bound_candidate_digest": support.SUPERSEDED_CANDIDATE},
            FindingReason.SLOT_SUPERSEDED_CANDIDATE,
            FactStatus.FAIL,
        ),
        ({"self_reported": True}, FindingReason.SLOT_SELF_REPORTED, FactStatus.FAIL),
    ],
)
def test_a_docs_slot_that_is_not_current_proof_refuses(
    changes: dict[str, Any], reason: FindingReason, status: FactStatus
) -> None:
    report = _report(
        support.replace_slot(support.record_answer(), support.DOCS_STAGE, _DOCS_SLOT, **changes)
    )

    assert report.verdict == "refused"
    assert report.refusals == ("missing-documentation-evidence",)
    assert _fact(report, support.DOCS_STAGE).status is status
    assert reason in _reasons(report, support.DOCS_STAGE)


def test_a_superseded_candidate_digest_turns_the_check_red_again() -> None:
    answer = support.record_answer()
    for stage_key, slot_key in (
        (support.DOCS_STAGE, _DOCS_SLOT),
        (support.REVIEW_STAGE, _REVIEW_SLOT),
    ):
        answer = support.replace_slot(
            answer, stage_key, slot_key, bound_candidate_digest=support.SUPERSEDED_CANDIDATE
        )
    report = _report(answer)

    assert report.refusals == (
        "missing-risk-derived-review-evidence",
        "missing-documentation-evidence",
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"disposition": "changes-requested"}, FindingReason.VERDICT_NOT_SIGNED_OFF),
        ({"disposition": "unknown"}, FindingReason.VERDICT_DISPOSITION_UNKNOWN),
        ({"self_reported": True}, FindingReason.VERDICT_SELF_REPORTED),
    ],
)
def test_a_verdict_that_is_not_an_independent_sign_off_refuses(
    changes: dict[str, Any], reason: FindingReason
) -> None:
    report = _report(
        support.replace_verdict(
            support.record_answer(),
            support.REVIEW_STAGE,
            _REVIEW_SLOT,
            "verdict-security",
            **changes,
        )
    )

    assert report.verdict == "refused"
    assert report.refusals == ("missing-risk-derived-review-evidence",)
    assert reason in _reasons(report, support.REVIEW_STAGE)


def test_a_stage_the_record_cannot_resolve_is_unknown_rather_than_passing() -> None:
    answer = support.record_answer()
    for stage in answer["stages"]:
        if stage["stage_key"] == support.DOCS_STAGE:
            stage["resolution"] = "unknown"
            stage["required_slots"] = []
    report = _report(answer)

    assert _fact(report, support.DOCS_STAGE).status is FactStatus.STATE_UNKNOWN
    assert _reasons(report, support.DOCS_STAGE) == (FindingReason.STAGE_UNRESOLVED,)
    assert report.refusals == ("missing-documentation-evidence",)


def test_a_stage_absent_from_the_record_answer_is_unknown_rather_than_passing() -> None:
    answer = support.record_answer()
    answer["stages"] = [
        stage for stage in answer["stages"] if stage["stage_key"] != support.DOCS_STAGE
    ]
    report = _report(answer)

    assert _fact(report, support.DOCS_STAGE).status is FactStatus.STATE_UNKNOWN
    assert report.refusals == ("missing-documentation-evidence",)


def test_facts_after_the_boundary_are_not_owed_at_the_boundary() -> None:
    report = _report(support.record_answer())

    assert [fact.stage_key for fact in report.facts][-1] == "release-preflight"
    assert support.LANDING_STAGE not in {fact.stage_key for fact in report.facts}
