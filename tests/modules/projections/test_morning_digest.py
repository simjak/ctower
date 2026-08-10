"""Morning digest projection truthfulness and deterministic artifact tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from ctower_kernel.projections.morning_digest import (
    DecisionBriefFact,
    DecisionChoiceFact,
    DigestRequestFact,
    DigestRulingFact,
    MorningDigest,
    ReadingState,
    SourceReading,
    UnreachedScope,
    project_morning_digest,
)

__all__: tuple[str, ...] = ()

_OPERATOR_ID = UUID("00000000-0000-7000-8000-000000000001")
_REQUEST_ID = UUID("00000000-0000-7000-8000-000000000101")
_EXECUTED_REQUEST_ID = UUID("00000000-0000-7000-8000-000000000102")
_UNRELATED_REQUEST_ID = UUID("00000000-0000-7000-8000-000000000103")
_RULING_ID = UUID("00000000-0000-7000-8000-000000000201")
_TODAY_RULING_ID = UUID("00000000-0000-7000-8000-000000000202")
_TICKET_ID = UUID("00000000-0000-7000-8000-000000000301")
_OPTIONAL_TICKET_ID = UUID("00000000-0000-7000-8000-000000000302")
_UNRELATED_TICKET_ID = UUID("00000000-0000-7000-8000-000000000303")
_OBSERVED_AT = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)
_DIGEST_DATE = date(2026, 8, 10)
_PROOF_ROW_COUNT = 2


def test_digest_composes_three_sections_and_prior_day_ruling_execution() -> None:
    requests = SourceReading.complete(
        (_open_decision(), _executed_request(), _unrelated_request()),
        watermark=41,
        observed_at=_OBSERVED_AT,
    )
    rulings = SourceReading.complete(
        (
            DigestRulingFact(
                ruling_id=_RULING_ID,
                project_key="ctower",
                verbatim="Proceed with the bounded option.",
                recorded_at=datetime(2026, 8, 9, 8, 15, tzinfo=UTC),
                linked_request_ids=(_EXECUTED_REQUEST_ID,),
            ),
            DigestRulingFact(
                ruling_id=_TODAY_RULING_ID,
                project_key="ctower",
                verbatim="This belongs to today's next digest.",
                recorded_at=datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
                linked_request_ids=(),
            ),
        ),
        watermark=44,
        observed_at=_OBSERVED_AT,
    )

    digest = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    _assert_complete_digest(digest)


def test_decision_choice_uses_the_canonical_zero_through_ten_scale() -> None:
    with pytest.raises(ValueError, match="0 through 10"):
        DecisionChoiceFact("A", "Continue.", 11)


def test_ruling_fact_refuses_a_naive_recording_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DigestRulingFact(
            ruling_id=_RULING_ID,
            project_key="ctower",
            verbatim="Proceed.",
            recorded_at=_OBSERVED_AT.replace(tzinfo=None),
            linked_request_ids=(),
        )


def test_unreached_request_source_is_unknown_never_a_zero() -> None:
    requests: SourceReading[DigestRequestFact] = SourceReading.unknown(
        UnreachedScope("requests", "503 Request source did not answer"),
        observed_at=_OBSERVED_AT,
    )
    rulings = SourceReading.complete(
        (
            DigestRulingFact(
                ruling_id=_RULING_ID,
                project_key="ctower",
                verbatim="Proceed with the bounded option.",
                recorded_at=datetime(2026, 8, 9, 8, 15, tzinfo=UTC),
                linked_request_ids=(_EXECUTED_REQUEST_ID,),
            ),
        ),
        watermark=44,
        observed_at=_OBSERVED_AT,
    )

    digest = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    assert digest.state is ReadingState.PARTIAL
    assert digest.open_decisions.state is ReadingState.UNKNOWN
    assert digest.open_decisions.total_count is None
    assert digest.open_decisions.visible_count == 0
    assert digest.proof.state is ReadingState.PARTIAL
    assert digest.proof.total_count is None
    assert digest.yesterday_rulings.visible_count == 1
    assert digest.yesterday_rulings.state is ReadingState.PARTIAL
    assert digest.yesterday_rulings.items[0].executions == ()
    assert digest.yesterday_rulings.items[0].unknown_reason == "request-source-unreached"


def test_unreached_ruling_source_makes_the_proof_total_unknown_never_zero() -> None:
    requests: SourceReading[DigestRequestFact] = SourceReading.complete(
        (), watermark=41, observed_at=_OBSERVED_AT
    )
    rulings: SourceReading[DigestRulingFact] = SourceReading.unknown(
        UnreachedScope("rulings", "ruling-source-unavailable"),
        observed_at=_OBSERVED_AT,
    )

    digest = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    assert digest.yesterday_rulings.state is ReadingState.UNKNOWN
    assert digest.proof.state is ReadingState.PARTIAL
    assert digest.proof.visible_count == 0
    assert digest.proof.total_count is None
    assert digest.proof.unreached == (UnreachedScope("rulings", "ruling-source-unavailable"),)


def test_partial_source_preserves_visible_rows_and_withholds_the_total() -> None:
    requests = SourceReading.partial(
        (_open_decision(),),
        watermark=41,
        observed_at=_OBSERVED_AT,
        unreached=(UnreachedScope("manibo", "bounded read exhausted"),),
    )
    rulings: SourceReading[DigestRulingFact] = SourceReading.complete(
        (), watermark=44, observed_at=_OBSERVED_AT
    )

    digest = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    assert digest.open_decisions.state is ReadingState.PARTIAL
    assert digest.open_decisions.visible_count == 1
    assert digest.open_decisions.total_count is None
    assert digest.open_decisions.unreached == (UnreachedScope("manibo", "bounded read exhausted"),)
    assert digest.yesterday_rulings.state is ReadingState.COMPLETE
    assert digest.yesterday_rulings.total_count == 0


def test_missing_typed_brief_and_execution_link_render_unknown_not_invented_content() -> None:
    request = DigestRequestFact(
        request_id=_REQUEST_ID,
        request_number=101,
        project_key="ctower",
        content="Choose the release window.",
        state="BLOCKED",
        owner_id=_OPERATOR_ID,
        blocker="operator-decision-required",
        source_kind="mission-control",
        source_ref="R101",
        required_ticket_ids=(),
        optional_ticket_ids=(),
        current_proof_count=0,
        decision_brief=None,
    )
    ruling = DigestRulingFact(
        ruling_id=_RULING_ID,
        project_key="ctower",
        verbatim="Proceed with the bounded option.",
        recorded_at=datetime(2026, 8, 9, 8, 15, tzinfo=UTC),
        linked_request_ids=None,
    )

    digest = project_morning_digest(
        SourceReading.complete((request,), watermark=41, observed_at=_OBSERVED_AT),
        SourceReading.complete((ruling,), watermark=44, observed_at=_OBSERVED_AT),
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    _assert_missing_links(digest)


def test_unknown_proof_count_marks_the_related_scope_partial() -> None:
    request = replace(_open_decision(), current_proof_count=None)

    digest = project_morning_digest(
        SourceReading.complete((request,), watermark=41, observed_at=_OBSERVED_AT),
        SourceReading.complete((), watermark=44, observed_at=_OBSERVED_AT),
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    assert digest.proof.state is ReadingState.PARTIAL
    assert digest.proof.total_count == 1
    assert digest.proof.items[0].current_proof_count is None
    assert digest.proof.unreached == (
        UnreachedScope("R101:proof-count", "proof-count-not-recorded"),
    )


def test_complete_empty_sources_are_measured_zeroes_and_artifact_digest_is_stable() -> None:
    requests: SourceReading[DigestRequestFact] = SourceReading.complete(
        (), watermark=41, observed_at=_OBSERVED_AT
    )
    rulings: SourceReading[DigestRulingFact] = SourceReading.complete(
        (), watermark=44, observed_at=_OBSERVED_AT
    )

    first = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )
    second = project_morning_digest(
        requests,
        rulings,
        digest_date=_DIGEST_DATE,
        observed_at=_OBSERVED_AT,
    )

    assert first.state is ReadingState.COMPLETE
    assert first.open_decisions.total_count == 0
    assert first.yesterday_rulings.total_count == 0
    assert first.proof.total_count == 0
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.artifact_sha256.startswith("sha256:")


def test_prior_civil_day_uses_the_vilnius_fall_back_boundary() -> None:
    first_id = UUID("00000000-0000-7000-8000-000000000211")
    final_id = UUID("00000000-0000-7000-8000-000000000212")
    excluded_id = UUID("00000000-0000-7000-8000-000000000213")
    rulings = SourceReading.complete(
        (
            DigestRulingFact(
                first_id,
                "ctower",
                "First hour.",
                datetime(2026, 10, 24, 21, 30, tzinfo=UTC),
                (),
            ),
            DigestRulingFact(
                final_id,
                "ctower",
                "Final hour.",
                datetime(2026, 10, 25, 21, 30, tzinfo=UTC),
                (),
            ),
            DigestRulingFact(
                excluded_id,
                "ctower",
                "Next civil day.",
                datetime(2026, 10, 25, 22, 30, tzinfo=UTC),
                (),
            ),
        ),
        watermark=45,
        observed_at=_OBSERVED_AT,
    )

    digest = project_morning_digest(
        SourceReading.complete((), watermark=41, observed_at=_OBSERVED_AT),
        rulings,
        digest_date=date(2026, 10, 26),
        observed_at=_OBSERVED_AT,
    )

    assert tuple(item.ruling_id for item in digest.yesterday_rulings.items) == (
        first_id,
        final_id,
    )


def _assert_complete_digest(digest: MorningDigest) -> None:
    assert digest.artifact_key == "morning-digest:2026-08-10:Europe/Vilnius"
    assert digest.state is ReadingState.COMPLETE
    assert digest.open_decisions.total_count == 1
    assert digest.open_decisions.items[0].brief.what == "Choose the release window."
    assert digest.open_decisions.items[0].brief.safe_default == "Keep the release on hold."
    assert digest.yesterday_rulings.total_count == 1
    execution = digest.yesterday_rulings.items[0].executions[0]
    assert execution.request_reference == "R102"
    assert execution.state == "DONE"
    assert execution.ticket_ids == (_TICKET_ID,)
    assert digest.proof.total_count == _PROOF_ROW_COUNT
    proof = next(item for item in digest.proof.items if item.request_reference == "R102")
    assert proof.current_proof_count == 1
    assert proof.tickets[0].href == f"/v1/tickets/{_TICKET_ID}/timeline"
    assert proof.tickets[0].purpose == "required"
    assert all(item.request_id != _UNRELATED_REQUEST_ID for item in digest.proof.items)


def _assert_missing_links(digest: MorningDigest) -> None:
    decision = digest.open_decisions.items[0]
    assert decision.state is ReadingState.PARTIAL
    assert decision.brief.what == "Choose the release window."
    assert decision.brief.choices == ()
    assert decision.brief.recommendation is None
    assert decision.brief.safe_default == "No action. This Request stays blocked."
    assert decision.unknown_reason == "decision-brief-not-recorded"
    assert digest.open_decisions.unreached == (
        UnreachedScope("R101:decision-brief", "decision-brief-not-recorded"),
    )
    projected_ruling = digest.yesterday_rulings.items[0]
    assert projected_ruling.executions == ()
    assert projected_ruling.unknown_reason == "execution-link-not-recorded"
    assert digest.yesterday_rulings.unreached == (
        UnreachedScope(f"ruling:{_RULING_ID}:execution-link", "execution-link-not-recorded"),
    )
    assert digest.state is ReadingState.PARTIAL


def _open_decision() -> DigestRequestFact:
    return DigestRequestFact(
        request_id=_REQUEST_ID,
        request_number=101,
        project_key="ctower",
        content="Choose the release window.",
        state="BLOCKED",
        owner_id=_OPERATOR_ID,
        blocker="operator-decision-required",
        source_kind="mission-control",
        source_ref="R101",
        required_ticket_ids=(),
        optional_ticket_ids=(_OPTIONAL_TICKET_ID,),
        current_proof_count=0,
        decision_brief=DecisionBriefFact(
            what="Choose the release window.",
            origin="The operator asked to avoid a dark release.",
            choices=(
                DecisionChoiceFact(
                    label="Release after proof",
                    outcome="The release waits for the named live proof.",
                    completeness=10,
                ),
                DecisionChoiceFact(
                    label="Keep holding",
                    outcome="No release occurs today.",
                    completeness=10,
                ),
            ),
            recommendation="Release after proof because it preserves the gate.",
            safe_default="Keep the release on hold.",
        ),
    )


def _executed_request() -> DigestRequestFact:
    return DigestRequestFact(
        request_id=_EXECUTED_REQUEST_ID,
        request_number=102,
        project_key="ctower",
        content="Ship the bounded change.",
        state="DONE",
        owner_id=UUID("00000000-0000-7000-8000-000000000002"),
        blocker=None,
        source_kind="mission-control",
        source_ref="R102",
        required_ticket_ids=(_TICKET_ID,),
        optional_ticket_ids=(),
        current_proof_count=1,
        decision_brief=None,
    )


def _unrelated_request() -> DigestRequestFact:
    return DigestRequestFact(
        request_id=_UNRELATED_REQUEST_ID,
        request_number=103,
        project_key="ctower",
        content="Unrelated historical work.",
        state="DONE",
        owner_id=_OPERATOR_ID,
        blocker=None,
        source_kind="mission-control",
        source_ref="R103",
        required_ticket_ids=(_UNRELATED_TICKET_ID,),
        optional_ticket_ids=(),
        current_proof_count=1,
        decision_brief=None,
    )
