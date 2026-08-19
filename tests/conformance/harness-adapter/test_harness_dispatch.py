"""AC-HAD-02 and AC-HAD-09 — delivery is never assumed, and nothing dispatches uncleared.

Two failures live here and both render as success if they are not tested. A brief sitting
unsent in a composer reports as delivered while the lane reads idle — indistinguishable from
finished — and a dispatch that skipped its guard looks exactly like one that cleared it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from harness_doubles import BASE_TIME, GUARD_VERSION, StubGuard, StubReceipts
from harness_subjects import BUILDERS, SubjectBuilder, subjects

from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.facts import DispatchReceipt
from ctower_runner_sdk.fake import Fault
from ctower_runner_sdk.guard import GuardVerdict
from ctower_runner_sdk.policy import input_refusal
from ctower_runner_sdk.refusals import Refusal

__all__: tuple[str, ...] = ()

_BUILDS = tuple(builder for _, builder in BUILDERS)
_IDS = tuple(name for name, _ in BUILDERS)
_UNACKNOWLEDGED: tuple[Fault, ...] = (
    "unacknowledged_dispatch",
    "queued_composer",
    "collapsed_paste",
)


def _spawn(subject: ConformanceSubject) -> DispatchReceipt | Refusal:
    inputs = subject.inputs
    return subject.binding.spawn(inputs.attempt, inputs.seat, inputs.brief, inputs.context)


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
    refusal = input_refusal(subject.binding.spec, "working")

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-capability-unsupported"
    assert input_refusal(subject.binding.spec, "idle") is None


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
