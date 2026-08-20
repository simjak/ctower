"""AC-HAD-02 and AC-HAD-09 — delivery is never assumed, and nothing dispatches uncleared.

Two failures live here and both render as success if they are not tested. A brief sitting
unsent in a composer reports as delivered while the lane reads idle — indistinguishable from
finished — and a dispatch that skipped its guard looks exactly like one that cleared it.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from harness_doubles import BASE_TIME, GUARD_VERSION, StubGuard, StubReceipts
from harness_subjects import BUILDERS, DOCUMENTS, DocumentBuilder, SubjectBuilder, subjects

from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.facts import DispatchReceipt
from ctower_runner_sdk.fake import Fault
from ctower_runner_sdk.guard import DispatchBoundary, ExecutionPlan, GuardVerdict
from ctower_runner_sdk.policy import input_refusal
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec

__all__: tuple[str, ...] = ()

_BUILDS = tuple(builder for _, builder in BUILDERS)
_IDS = tuple(name for name, _ in BUILDERS)
_DOCUMENTS = tuple(document for _, document in DOCUMENTS)
_DOC_IDS = tuple(name for name, _ in DOCUMENTS)
_UNACKNOWLEDGED: tuple[Fault, ...] = (
    "unacknowledged_dispatch",
    "queued_composer",
    "collapsed_paste",
)


def _spawn(subject: ConformanceSubject) -> DispatchReceipt | Refusal:
    inputs = subject.inputs
    return subject.binding.spawn(inputs.attempt, inputs.seat, inputs.brief, inputs.context)


def _capabilities(document: dict[str, object]) -> list[str]:
    declared = document["capabilities"]
    assert isinstance(declared, list)
    return [str(item) for item in declared]


def _plan(
    *,
    harness_ref: str = "hermes",
    profile_ref: str = "engineer",
    composition_digest: str = "hermes@1+sha256:a",
    program: str = "hermes",
    argv: tuple[str, ...] = ("engineer-t1",),
    worktree_path: str = "/srv/attempt",
) -> ExecutionPlan:
    return ExecutionPlan(
        harness_ref=harness_ref,
        profile_ref=profile_ref,
        composition_digest=composition_digest,
        program=program,
        argv=argv,
        worktree_path=worktree_path,
    )


# Each pair is two DIFFERENT plans that a boundary-forging separator would write
# identically. Every member is reachable: `harness_ref` and `profile_ref` arrive observed,
# and an argument may carry a newline.
_FORGED_PAIRS: tuple[tuple[ExecutionPlan, ExecutionPlan], ...] = (
    (
        _plan(profile_ref="engineer\nhermes@1+sha256:a", composition_digest="x"),
        _plan(profile_ref="engineer", composition_digest="hermes@1+sha256:a\nx"),
    ),
    (
        _plan(harness_ref="hermes\nengineer", profile_ref="reviewer"),
        _plan(harness_ref="hermes", profile_ref="engineer\nreviewer"),
    ),
    (
        _plan(argv=("engineer-t1\n/srv/attempt",)),
        _plan(argv=("engineer-t1",), worktree_path="/srv/attempt\n/srv/attempt"),
    ),
)
_PAIR_IDS = ("observed-profile", "observed-harness", "argument-tail")


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_a_clean_dispatch_returns_a_receipt_carrying_the_durable_command_id(
    subject: ConformanceSubject,
) -> None:
    receipt = _spawn(subject)

    assert isinstance(receipt, DispatchReceipt), receipt
    assert receipt.durable_command_id
    assert receipt.guard_decision_id == "decision-1"
    assert receipt.composition_digest == subject.inputs.attempt.composition_digest


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
@pytest.mark.parametrize("fault", _UNACKNOWLEDGED)
def test_an_unacknowledged_composer_refuses_with_zero_session_start_fact(
    build: SubjectBuilder, fault: Fault
) -> None:
    subject = build()
    subject.control.inject(fault)

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-unacknowledged"
    assert not [item for item in subject.control.mutations() if item.startswith("session-start")]
    assert not [item for item in subject.control.mutations() if item.startswith("writeback")]


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_input_into_a_working_lane_needs_the_declared_interrupt_capability(
    subject: ConformanceSubject,
) -> None:
    """The declaration decides, and only the declaration.

    Every binding bound today happens to lack this capability, so an unconditional refusal
    passes and reads like law. It is not law, it is the current fleet: the next harness whose
    steering model is an interrupt would fail this suite on the day it registers, and the
    suite would be edited to fit it — which is exactly what the one unchanged suite exists to
    prevent. The rule is `iff`, in both directions, for every subject.
    """

    spec = subject.binding.spec
    refusal = input_refusal(spec, "working")

    if spec.declares("INTERRUPT_AND_RESUME"):
        assert refusal is None
    else:
        assert isinstance(refusal, Refusal), refusal
        assert refusal.name == "harness-capability-unsupported"
        assert dict(refusal.detail)["capability"] == "INTERRUPT_AND_RESUME"
    assert input_refusal(spec, "idle") is None


@pytest.mark.parametrize("document", _DOCUMENTS, ids=_DOC_IDS)
def test_a_binding_that_declares_the_interrupt_capability_takes_input_while_working(
    document: DocumentBuilder,
) -> None:
    """The positive half of the same `iff`, pinned before a binding needs it.

    An interrupt-capable harness is authored data away from every subject here, so the world
    the cell above refuses in is proven against the world it must accept in — from the same
    documents, through the same contract, with one capability declared.
    """

    declared = document()
    declared["capabilities"] = sorted({*_capabilities(declared), "INTERRUPT_AND_RESUME"})
    spec = parse_harness_spec(declared)

    assert isinstance(spec, HarnessSpec), spec
    assert spec.declares("INTERRUPT_AND_RESUME")
    assert input_refusal(spec, "working") is None


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
@pytest.mark.parametrize(
    ("verdict", "expected"),
    (
        ("block", "harness-dispatch-blocked"),
        ("needs_operator", "harness-dispatch-needs-operator"),
    ),
)
def test_a_blocked_or_operator_gated_plan_dispatches_nothing(
    build: SubjectBuilder, verdict: GuardVerdict, expected: str
) -> None:
    subject = build(guard=StubGuard(verdict))

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == expected
    assert not [item for item in subject.control.mutations() if item.startswith("launch")]
    assert not [item for item in subject.control.mutations() if item.startswith("session-start")]


@pytest.mark.parametrize("pair", _FORGED_PAIRS, ids=_PAIR_IDS)
def test_two_different_plans_never_share_one_normalized_digest(
    pair: tuple[ExecutionPlan, ExecutionPlan],
) -> None:
    """AC-HAD-09 binds a decision to the exact plan, which needs the digest to be exact.

    A separator between fields is only a boundary while no field can contain it. These two
    plans differ in which field a value belongs to, and a digest that cannot tell them apart
    hands one plan's clearance to the other.
    """

    first, second = pair

    assert first != second
    assert first.normalized_digest() != second.normalized_digest()


@pytest.mark.parametrize("pair", _FORGED_PAIRS, ids=_PAIR_IDS)
def test_a_grant_minted_for_a_twin_plan_does_not_clear_this_one(
    pair: tuple[ExecutionPlan, ExecutionPlan],
) -> None:
    twin, presented = pair
    boundary = DispatchBoundary(
        StubGuard(plan_digest=twin.normalized_digest()), StubReceipts(), GUARD_VERSION
    )

    refusal = boundary.clear(presented, BASE_TIME)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-guard-decision-invalid"
    assert "different normalized plan" in refusal.observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_decision_about_a_different_plan_fails_closed(build: SubjectBuilder) -> None:
    subject = build(guard=StubGuard(plan_digest="sha256:" + "0" * 64))

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-guard-decision-invalid"
    assert "different normalized plan" in refusal.observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_an_expired_grant_fails_closed(build: SubjectBuilder) -> None:
    subject = build(guard=StubGuard(expires_at=BASE_TIME - timedelta(minutes=1)))

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-guard-decision-invalid"
    assert "expired" in refusal.observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_grant_from_another_guard_version_fails_closed(build: SubjectBuilder) -> None:
    subject = build(guard=StubGuard(guard_version=GUARD_VERSION - 1))

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-guard-decision-invalid"
    assert "guard version" in refusal.observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_replayed_grant_fails_closed_on_its_second_use(build: SubjectBuilder) -> None:
    subject = build()

    first = _spawn(subject)
    second = _spawn(subject)

    assert isinstance(first, DispatchReceipt), first
    assert isinstance(second, Refusal), second
    assert second.name == "harness-guard-decision-invalid"
    assert "already used once" in second.observed


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_receipt_that_cannot_be_recorded_first_yields_zero_dispatch(
    build: SubjectBuilder,
) -> None:
    subject = build(receipts=StubReceipts(durable=False))

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-receipt-undurable"
    assert not [item for item in subject.control.mutations() if item.startswith("launch")]


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_every_dispatch_asks_the_guard_about_the_exact_plan_it_would_run(
    build: SubjectBuilder,
) -> None:
    guard = StubGuard()
    subject = build(guard=guard)

    receipt = _spawn(subject)

    assert isinstance(receipt, DispatchReceipt), receipt
    assert len(guard.asked) == 1
    launched = [item for item in subject.control.mutations() if item.startswith("launch:")]
    assert all(guard.asked[0] in item for item in launched)


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_blocked_plan_is_still_asked_about_before_it_is_refused(
    build: SubjectBuilder,
) -> None:
    guard = StubGuard("block")
    subject = build(guard=guard)

    refusal = _spawn(subject)

    assert isinstance(refusal, Refusal), refusal
    assert len(guard.asked) == 1
    assert not [item for item in subject.control.mutations() if item.startswith("launch:")]


@pytest.mark.parametrize("pin_field", ("harness_ref", "spec_revision", "composition_digest"))
@pytest.mark.parametrize(
    "subject",
    tuple(subject for subject in subjects() if subject.binding_class == "real"),
    ids=lambda item: item.name,
)
def test_every_real_binding_refuses_each_stale_composition_pin_before_any_mutation(
    subject: ConformanceSubject, pin_field: str
) -> None:
    """Every real binding rejects every stale pin before acquiring or launching."""

    current = subject.inputs.attempt
    stale_values: dict[str, object] = {
        "harness_ref": f"{current.harness_ref}-stale",
        "spec_revision": current.spec_revision + 100,
        "composition_digest": "forged-composition-digest",
    }
    stale = dataclasses.replace(current, **{pin_field: stale_values[pin_field]})

    refusal = subject.binding.spawn(
        stale,
        subject.inputs.seat,
        subject.inputs.brief,
        subject.inputs.context,
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-dispatch-pin-mismatch"
    assert dict(refusal.detail)["mismatched_fields"] == pin_field
    assert subject.control.mutations() == ()
