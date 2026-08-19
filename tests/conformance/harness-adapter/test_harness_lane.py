"""AC-HAD-05, AC-HAD-06 and AC-HAD-07 — authority, evidence, and how a lane ends.

Three lessons, all of them paid for. Seats must file as themselves, because with one shared
identity behind many seats the server has nothing to refuse against. A fix that is not
committed is not a fix. And a lane that ends without a checkpoint takes the work and the
continuation with it.
"""

from __future__ import annotations

import dataclasses

import pytest
from harness_doubles import BASE_TIME
from harness_subjects import BUILDERS, SEAT_PROJECT, SubjectBuilder, seat_credential, subjects

from ctower_runner_sdk.conformance import ConformanceSubject
from ctower_runner_sdk.facts import ArtifactSet, TeardownReceipt, WritebackFact, WritebackReceipt
from ctower_runner_sdk.fake import Fault
from ctower_runner_sdk.policy import TEARDOWN_TRIGGERS, WRITEBACK_SCOPES, teardown_receipt
from ctower_runner_sdk.refusals import Refusal

__all__: tuple[str, ...] = ()

_BUILDS = tuple(builder for _, builder in BUILDERS)
_IDS = tuple(name for name, _ in BUILDERS)
_HANDOFF_SECTIONS = ("done", "in_progress", "not_started", "next_three_steps")
_PANE_WORDS = ("pane", "capture", "terminal", "session_exists")
_CHECKPOINT_FAULTS: tuple[Fault, ...] = ("cap_menu", "context_saturation")

_FACTS = (
    WritebackFact(scope="capture", kind="session-observation"),
    WritebackFact(scope="evidence", kind="gate-closing-lines"),
    WritebackFact(scope="transition", kind="stage-advance"),
)


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_stage_change_is_emitted_as_a_request_and_the_answer_reported_verbatim(
    build: SubjectBuilder,
) -> None:
    subject = build()

    receipt = subject.binding.writeback(
        subject.inputs.attempt, subject.inputs.seat, subject.credential, _FACTS
    )

    assert isinstance(receipt, WritebackReceipt), receipt
    assert receipt.transition_requests == ("stage-advance",)
    assert "stage-advance" not in receipt.accepted
    assert receipt.actor_principal_id.endswith(subject.credential.seat_key)


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
@pytest.mark.parametrize("scope", ("operator", "commander"))
def test_an_operator_or_commander_credential_is_refused_rather_than_used(
    build: SubjectBuilder, scope: str
) -> None:
    subject = build()

    refusal = subject.binding.writeback(
        subject.inputs.attempt, subject.inputs.seat, seat_credential(scope=scope), _FACTS
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-credential-forbidden"
    assert not [item for item in subject.control.mutations() if item.startswith("writeback")]


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_foreign_project_key_is_denied_with_zero_disclosure(build: SubjectBuilder) -> None:
    subject = build()
    foreign = "another-company"

    refusal = subject.binding.writeback(
        subject.inputs.attempt, subject.inputs.seat, seat_credential(project_key=foreign), _FACTS
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "project-scope-denied"
    body = str(refusal.to_mapping())
    assert foreign not in body
    assert SEAT_PROJECT not in body
    assert not [item for item in subject.control.mutations() if item.startswith("writeback")]


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_fact_outside_the_three_scopes_refuses_by_name_with_zero_mutation(
    build: SubjectBuilder,
) -> None:
    subject = build()
    wider = (WritebackFact(scope="issuance", kind="mint-a-credential"),)  # type: ignore[arg-type]

    refusal = subject.binding.writeback(
        subject.inputs.attempt, subject.inputs.seat, subject.credential, wider
    )

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-writeback-scope-refused"
    assert "issuance" in refusal.observed
    assert not [item for item in subject.control.mutations() if item.startswith("writeback")]


def test_the_three_scopes_are_exhaustive() -> None:
    assert frozenset({"capture", "transition", "evidence"}) == WRITEBACK_SCOPES


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_an_uncommitted_worktree_refuses_and_names_the_dirty_paths(
    build: SubjectBuilder,
) -> None:
    subject = build()
    dirty = ("tools/ctower-beat-watchdog", "board/monitor-evidence.md")
    subject.control.set_tree(dirty=dirty, pushed=True)

    refusal = subject.binding.collect(subject.inputs.attempt, "checkpoint")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "checkpoint-uncollectable"
    assert [value for key, value in refusal.detail if key == "dirty_path"] == list(dirty)


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_a_run_with_no_status_artifact_still_collects_from_its_pushed_branch(
    build: SubjectBuilder,
) -> None:
    subject = build()
    subject.control.set_status_artifact(present=False)

    artifacts = subject.binding.collect(subject.inputs.attempt, "terminal")

    assert isinstance(artifacts, ArtifactSet), artifacts
    assert artifacts.status_artifact_path is None
    assert artifacts.is_complete()
    assert artifacts.handoff is not None


def test_no_artifact_slot_can_be_satisfied_from_pane_text() -> None:
    fields = {field.name for field in dataclasses.fields(ArtifactSet)}

    assert not [name for name in fields if any(word in name for word in _PANE_WORDS)]
    assert {"branch", "head_sha", "pushed"} <= fields


def test_saturation_and_cap_are_the_states_that_trigger_a_checkpoint() -> None:
    assert frozenset({"saturated", "capped"}) == TEARDOWN_TRIGGERS


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
@pytest.mark.parametrize("fault", _CHECKPOINT_FAULTS)
def test_a_capped_or_saturated_lane_checkpoints_with_a_four_section_handoff(
    build: SubjectBuilder, fault: Fault
) -> None:
    subject = build()
    subject.control.inject(fault)

    receipt = subject.binding.teardown(subject.inputs.attempt, "checkpoint")

    assert isinstance(receipt, TeardownReceipt), receipt
    assert receipt.artifacts is not None
    assert receipt.artifacts.pushed
    assert receipt.artifacts.handoff is not None
    assert receipt.artifacts.handoff.sections() == _HANDOFF_SECTIONS


def test_a_park_without_a_stated_basis_fails_loud() -> None:
    refusal = teardown_receipt(
        "park", artifacts=None, state="idle", sole_work_unpushed=False, expires_at=BASE_TIME
    )

    assert isinstance(refusal, Refusal)
    assert refusal.name == "park-basis-broken"


def test_a_park_without_an_explicit_expiry_fails_loud() -> None:
    refusal = teardown_receipt(
        "park", artifacts=None, state="idle", sole_work_unpushed=False, basis="waiting on a reset"
    )

    assert isinstance(refusal, Refusal)
    assert refusal.name == "park-expired"


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_reap_refuses_while_this_lane_holds_the_only_unpushed_copy(
    build: SubjectBuilder,
) -> None:
    subject = build()
    subject.control.set_tree(dirty=(), pushed=False)

    refusal = subject.binding.teardown(subject.inputs.attempt, "reap")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "teardown-would-destroy-sole-work"


@pytest.mark.parametrize("build", _BUILDS, ids=_IDS)
def test_reap_refuses_a_dead_auth_lane_and_preserves_it_for_resume(
    build: SubjectBuilder,
) -> None:
    subject = build()
    subject.control.inject("dead_auth")

    refusal = subject.binding.teardown(subject.inputs.attempt, "reap")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "teardown-refused-dead-auth"
    assert "resume" in refusal.meaning


@pytest.mark.parametrize("subject", subjects(), ids=lambda item: item.name)
def test_a_reap_that_is_allowed_records_that_a_nudge_was_offered_first(
    subject: ConformanceSubject,
) -> None:
    receipt = subject.binding.teardown(subject.inputs.attempt, "reap")

    assert isinstance(receipt, TeardownReceipt), receipt
    assert receipt.nudge_offered
