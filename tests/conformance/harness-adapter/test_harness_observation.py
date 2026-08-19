"""AC-HAD-03, AC-HAD-04 and AC-HAD-08 — what a lane's state actually is.

Each of these is a failure that renders as the healthy state, which is why the corpus is
part of the contract rather than part of the implementation. The first saturation detector
on this fleet matched nothing at all and would have reported a clean fleet forever.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from harness_doubles import BASE_TIME
from harness_subjects import BUILDERS, SubjectBuilder, build_hermes, judgment_inputs, subjects

from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.facts import NOT_WORKING, ModelObservation
from ctower_runner_sdk.policy import ladder_disposition, undeclared_source_refusal
from ctower_runner_sdk.refusals import Refusal, substrate_unobservable

__all__: tuple[str, ...] = ()

_BUILDS = tuple(builder for _, builder in BUILDERS)
_IDS = tuple(name for name, _ in BUILDERS)
_MIN_CAPTURED_CASES = 4


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_every_corpus_sample_classifies_to_the_state_it_declares(
    subject: ConformanceSubject,
) -> None:
    for case in subject.control.corpus():
        assert subject.control.classify(case.sample) == case.expected, case.label


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_every_corpus_case_states_where_it_came_from(subject: ConformanceSubject) -> None:
    for case in subject.control.corpus():
        assert case.provenance.strip(), case.label


def test_a_real_binding_ships_captured_substrate_output_and_not_only_composed_samples() -> None:
    subject = build_hermes()

    captured = [case for case in subject.control.corpus() if case.captured]

    assert len(captured) >= _MIN_CAPTURED_CASES
    assert all("captured" in case.provenance for case in captured)


def test_the_percentage_and_not_the_absolute_count_decides_saturation() -> None:
    control = build_hermes().control
    corpus = {case.label: case for case in control.corpus()}
    healthy = corpus["large-window lane at a high absolute token count is healthy"]
    saturated = corpus["past the window the lane is saturated while it is still emitting"]

    assert "295K" in healthy.sample and control.classify(healthy.sample) == "working"
    assert "178K" in saturated.sample and control.classify(saturated.sample) == "saturated"


def test_a_coverage_percentage_in_scrolled_output_does_not_trip_the_bar() -> None:
    control = build_hermes().control
    sample = next(case.sample for case in control.corpus() if "coverage percentage" in case.label)

    assert "95%" in sample
    assert control.classify(sample) == "idle"


def test_cap_and_saturation_both_count_as_not_working() -> None:
    control = build_hermes().control

    states = {case.expected for case in control.corpus() if case.expected != "working"}

    assert states <= NOT_WORKING
    assert {"capped", "saturated", "dead_auth"} <= states


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_silent_substitution_is_reported_as_a_conflict_and_never_as_agreement(
    build: SubjectBuilder,
) -> None:
    subject = build()
    subject.control.inject("model_substitution")

    fact = subject.binding.liveness(subject.inputs.attempt, 0)

    assert fact.served_model is not None
    assert fact.served_model.is_serving_truth()
    assert fact.conflict is not None
    assert "request" in fact.conflict


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_an_agreeing_footer_records_no_conflict(build: SubjectBuilder) -> None:
    subject = build()

    fact = subject.binding.liveness(subject.inputs.attempt, 0)

    assert fact.conflict is None


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_an_unobservable_substrate_is_named_and_never_guessed(build: SubjectBuilder) -> None:
    subject = build()
    subject.control.inject("pane_loss")

    fact = subject.binding.liveness(subject.inputs.attempt, 0)

    assert fact.state == "unknown"
    assert fact.probe.startswith("substrate-unobservable:")
    assert not fact.counts_as_working()


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_a_seat_self_report_satisfies_neither_source_and_refuses_by_name(
    subject: ConformanceSubject,
) -> None:
    claim = ModelObservation(
        value="whatever-the-seat-says",
        source="seat_self_report",
        proves="serving",
        observed_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
    )

    refusal = undeclared_source_refusal(subject.binding.spec, (claim,))

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-served-model-self-reported"


def test_the_unobservable_refusal_names_the_probe_that_failed() -> None:
    refusal = substrate_unobservable("hermes-capture-pane")

    assert refusal.name == "substrate-unobservable:hermes-capture-pane"
    assert "alive" in refusal.meaning


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_an_unknown_harness_value_is_carried_byte_for_byte_through_the_seam(
    build: SubjectBuilder,
) -> None:
    subject = build()
    observed = "  Hermes/FORK v2  "
    pinned = subject.inputs.attempt

    carried = type(pinned)(
        attempt_id=pinned.attempt_id,
        epoch=pinned.epoch,
        harness_ref=observed,
        profile_ref=pinned.profile_ref,
        spec_revision=pinned.spec_revision,
        composition_digest=pinned.composition_digest,
    )

    assert carried.to_mapping()["harness_ref"] == observed
    assert carried.with_lease(pinned.attempt_id).harness_ref == observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_later_epoch_supersedes_an_older_one_and_never_the_reverse(
    build: SubjectBuilder,
) -> None:
    subject = build()
    first = subject.inputs.attempt
    second = type(first)(
        attempt_id=first.attempt_id,
        epoch=first.epoch + 1,
        harness_ref=first.harness_ref,
        profile_ref=first.profile_ref,
        spec_revision=first.spec_revision,
        composition_digest=first.composition_digest,
    )

    assert second.supersedes(first)
    assert not first.supersedes(second)


def test_every_liveness_fact_carries_the_probe_that_produced_it() -> None:
    subject = build_hermes()

    fact = subject.binding.liveness(subject.inputs.attempt, 7)

    assert fact.probe
    assert fact.observed_at > BASE_TIME
    assert "cursor 7" in fact.evidence


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_declared_rung_of_the_spawn_intent_is_the_ladder_and_not_a_substitution(
    build: SubjectBuilder,
) -> None:
    subject = build()
    attempt = subject.inputs.attempt

    assert ladder_disposition(attempt, attempt.intent_model) == "as_intended"
    assert ladder_disposition(attempt, attempt.declared_rungs[0]) == "ladder"
    assert ladder_disposition(attempt, "a-model-no-rung-declares") == "substitution"


def test_a_judgment_lane_tolerates_no_rung_at_all() -> None:
    subject = build_hermes()
    judgment = judgment_inputs(subject.binding.spec).attempt

    assert judgment.judgment_lane
    assert ladder_disposition(judgment, judgment.intent_model) == "as_intended"
    assert ladder_disposition(judgment, judgment.declared_rungs[0]) == "substitution"


def test_the_ladder_is_anchored_to_the_spawn_intent_and_not_to_the_last_observation() -> None:
    subject = build_hermes()
    attempt = subject.inputs.attempt
    recovered = attempt.with_lease(attempt.attempt_id)

    assert recovered.intent_model == attempt.intent_model
    assert recovered.declared_rungs == attempt.declared_rungs
    assert ladder_disposition(recovered, attempt.declared_rungs[1]) == "ladder"


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_substitution_is_reported_on_the_liveness_fact_itself(
    build: SubjectBuilder,
) -> None:
    subject = build()
    subject.control.inject("model_substitution")

    fact = subject.binding.liveness(subject.inputs.attempt, 0)

    assert fact.ladder == "substitution"
    assert fact.to_mapping()["ladder"] == "substitution"
