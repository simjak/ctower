"""Shared lifecycle acceptance: receipts stop every real binding exactly once."""

from __future__ import annotations

import pytest
from harness_subjects import BUILDERS, SubjectBuilder

from ctower_runner_sdk import policy
from ctower_runner_sdk.facts import TeardownReceipt
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.seam import TeardownOrder

__all__: tuple[str, ...] = ()

_REAL_BUILDERS: tuple[tuple[str, SubjectBuilder], ...] = tuple(
    (name, builder) for name, builder in BUILDERS if name != "fault-injection-fake"
)
_ORDERS: tuple[TeardownOrder, ...] = ("checkpoint", "park", "reap")


@pytest.mark.parametrize(
    ("name", "builder"),
    _REAL_BUILDERS,
    ids=tuple(name for name, _ in _REAL_BUILDERS),
)
@pytest.mark.parametrize("order", _ORDERS)
def test_successful_teardown_terminates_each_real_binding_once_after_its_receipt(
    name: str, builder: SubjectBuilder, order: TeardownOrder
) -> None:
    del name
    subject = builder()
    before = subject.control.mutations()

    receipt = subject.binding.teardown(subject.inputs.attempt, order)

    assert isinstance(receipt, TeardownReceipt), receipt
    after = subject.control.mutations()[len(before) :]
    assert len(after) == 1
    assert after[0].startswith("terminate:")


def test_termination_failure_is_typed_and_loud() -> None:
    assert hasattr(policy, "terminate_after_receipt")
    subject = _REAL_BUILDERS[0][1]()
    receipt = TeardownReceipt(order="checkpoint", artifacts=None)

    outcome = policy.terminate_after_receipt(receipt, subject.inputs.attempt, lambda _: False)

    assert isinstance(outcome, Refusal), outcome
    assert outcome.name == "harness-termination-failed"


def test_refused_teardown_performs_zero_termination() -> None:
    subject = _REAL_BUILDERS[0][1]()
    subject.control.set_tree(dirty=("uncommitted.md",), pushed=True)
    before = subject.control.mutations()

    refusal = subject.binding.teardown(subject.inputs.attempt, "checkpoint")

    assert isinstance(refusal, Refusal), refusal
    assert subject.control.mutations() == before
