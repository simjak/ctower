"""Refusal-branch coverage for the authored workflow graph invariants."""

from __future__ import annotations

import pytest

from ctower_kernel.workflow._graph import (
    ActivityClass,
    Stage,
    Transition,
    WorkflowEntryEffect,
    WorkflowGraph,
)


def _stage(key: str) -> Stage:
    return Stage(key=key, activity_class=ActivityClass.WORK)


def _transition(source: str = "intake", destination: str = "think") -> Transition:
    return Transition(source=source, destination=destination, predicate_ref="gates@1")


def _graph(**overrides: object) -> WorkflowGraph:
    fields: dict[str, object] = {
        "key": "engineering.sample",
        "revision": 1,
        "initial_stage": "intake",
        "stages": (_stage("intake"), _stage("think")),
        "transitions": (_transition(),),
    }
    fields.update(overrides)
    return WorkflowGraph(**fields)  # type: ignore[arg-type]


def test_stage_key_must_be_stable() -> None:
    with pytest.raises(ValueError, match="stage key must be stable"):
        _stage("Not Stable!")


def test_stage_entry_effects_must_be_unique() -> None:
    effect = next(iter(WorkflowEntryEffect))
    with pytest.raises(ValueError, match="entry effects must be unique"):
        Stage(key="intake", activity_class=ActivityClass.WORK, entry_effects=(effect, effect))


def test_transition_source_must_be_stable() -> None:
    with pytest.raises(ValueError, match="transition source must be stable"):
        _transition(source="Bad Source")


def test_transition_destination_must_be_stable() -> None:
    with pytest.raises(ValueError, match="transition destination must be stable"):
        _transition(destination="Bad Destination")


def test_transition_predicate_must_be_versioned() -> None:
    with pytest.raises(ValueError, match="transition predicate must be versioned"):
        Transition(source="intake", destination="think", predicate_ref="unversioned")


def test_workflow_key_must_be_stable() -> None:
    with pytest.raises(ValueError, match="workflow key must be stable"):
        _graph(key="Not Stable!")


def test_workflow_revision_must_be_positive() -> None:
    with pytest.raises(ValueError, match="workflow revision must be positive"):
        _graph(revision=0)


def test_workflow_stages_must_be_nonempty_and_unique() -> None:
    with pytest.raises(ValueError, match="stages must be nonempty and unique"):
        _graph(stages=(), transitions=())
    with pytest.raises(ValueError, match="stages must be nonempty and unique"):
        _graph(stages=(_stage("intake"), _stage("intake")))


def test_workflow_initial_stage_must_be_declared() -> None:
    with pytest.raises(ValueError, match="initial stage must reference one declared stage"):
        _graph(initial_stage="missing")


def test_workflow_edges_must_be_unique() -> None:
    with pytest.raises(ValueError, match="edges must be unique"):
        _graph(transitions=(_transition(), _transition()))


def test_workflow_edges_must_reference_declared_stages() -> None:
    with pytest.raises(ValueError, match="edges must reference declared stages"):
        _graph(transitions=(_transition(destination="missing"),))


def test_workflow_policy_references_must_be_versioned() -> None:
    with pytest.raises(ValueError, match="policy references must be versioned"):
        _graph(execution_policy_ref="unversioned")
    with pytest.raises(ValueError, match="policy references must be versioned"):
        _graph(gate_policy_ref="unversioned")


def test_workflow_reference_is_key_at_revision() -> None:
    assert _graph().reference == "engineering.sample@1"
