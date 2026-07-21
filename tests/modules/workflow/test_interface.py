"""Public Workflow Interface tracer tests."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from ctower_kernel.workflow import (
    ActivityClass,
    Stage,
    Transition,
    Workflow,
    WorkflowCommand,
    WorkflowContextSnapshot,
    WorkflowGraph,
    WorkflowStart,
)

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()


def _graph(*, key: str = "fixture.generic", revision: int = 1) -> WorkflowGraph:
    return WorkflowGraph(
        key=key,
        revision=revision,
        initial_stage="alpha",
        stages=(
            Stage("alpha", ActivityClass.WORK),
            Stage("beta", ActivityClass.VERIFICATION),
            Stage("omega", ActivityClass.WORK),
        ),
        transitions=(
            Transition("alpha", "beta", "predicate.ready@1"),
            Transition("beta", "omega", "predicate.proved@1"),
        ),
    )


def test_versioned_graph_allows_only_declared_edges_and_derives_activity() -> None:
    graph = _graph()
    policy_digests = {
        "fixture.execution@1": "sha256:" + "1" * 64,
        "fixture.gates@1": "sha256:" + "2" * 64,
        "fixture.evidence@1": "sha256:" + "3" * 64,
    }
    workflow = Workflow((graph,), policy_digests=policy_digests)

    accepted = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.ready@1"}),
            run_started=True,
        ),
        WorkflowCommand(destination_stage="beta"),
    )
    undeclared = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.proved@1"}),
            run_started=True,
        ),
        WorkflowCommand(destination_stage="omega"),
    )

    assert accepted.accepted is True
    assert accepted.activity_class is ActivityClass.VERIFICATION
    assert accepted.predicate_ref == "predicate.ready@1"
    assert undeclared.accepted is False
    assert undeclared.reason == "transition-not-declared"


def test_version_and_predicate_mismatches_fail_closed() -> None:
    workflow = Workflow((_graph(),))

    unknown_version = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@2",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.ready@1"}),
            run_started=True,
        ),
        WorkflowCommand(destination_stage="beta"),
    )
    missing_predicate = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset(),
            run_started=True,
        ),
        WorkflowCommand(destination_stage="beta"),
    )

    assert unknown_version.accepted is False
    assert unknown_version.reason == "workflow-version-unknown"
    assert missing_predicate.accepted is False
    assert missing_predicate.reason == "predicate-unsatisfied"


def test_transition_refuses_to_invent_an_absent_run() -> None:
    workflow = Workflow((_graph(),))

    skipped = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="beta",
            satisfied_predicates=frozenset({"predicate.proved@1"}),
            run_started=False,
        ),
        WorkflowCommand(destination_stage="omega"),
    )
    initial = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.ready@1"}),
            run_started=False,
        ),
        WorkflowCommand(destination_stage="beta"),
    )

    assert skipped.accepted is False
    assert skipped.reason == "run-not-started"
    assert initial.accepted is False
    assert initial.reason == "run-not-started"


def test_start_pin_is_exact_and_uses_authored_initial_stage() -> None:
    graph = WorkflowGraph(
        key="fixture.generic",
        revision=1,
        initial_stage="alpha",
        stages=(Stage("alpha", ActivityClass.WORK),),
        transitions=(),
        execution_policy_ref="fixture.execution@1",
        gate_policy_ref="fixture.gates@1",
    )
    workflow = Workflow(
        (graph,),
        policy_digests={
            "fixture.execution@1": "sha256:" + "1" * 64,
            "fixture.gates@1": "sha256:" + "2" * 64,
            "fixture.evidence@1": "sha256:" + "3" * 64,
        },
    )
    start = WorkflowStart(
        client_command_id=__import__("uuid").uuid4(),
        ticket_id=__import__("uuid").uuid4(),
        workflow_ref=graph.reference,
        workflow_digest=graph.digest,
        execution_policy_ref="fixture.execution@1",
        execution_policy_digest="sha256:" + "1" * 64,
        gate_policy_ref="fixture.gates@1",
        gate_policy_digest="sha256:" + "2" * 64,
        evidence_policy_ref="fixture.evidence@1",
        evidence_policy_digest="sha256:" + "3" * 64,
    )

    accepted = workflow.validate_start(start)
    changed_digest = workflow.validate_start(replace(start, workflow_digest="sha256:" + "f" * 64))
    changed_policy = workflow.validate_start(
        replace(start, evidence_policy_digest="sha256:" + "f" * 64)
    )

    assert accepted.accepted is True
    assert accepted.initial_stage == "alpha"
    assert accepted.activity_class is ActivityClass.WORK
    assert changed_digest.accepted is False
    assert changed_digest.reason == "workflow-pin-mismatch"
    assert changed_policy.accepted is False
    assert changed_policy.reason == "workflow-pin-mismatch"


def test_authored_fixture_loads_and_uses_pinned_graph_data() -> None:
    payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    graph = WorkflowGraph.from_mapping(payload)
    decision = Workflow((graph,)).evaluate(
        WorkflowContextSnapshot(
            workflow_ref="ctower.trust-spine-four-stage@1",
            current_stage="frame",
            satisfied_predicates=frozenset({"criteria.frozen@1"}),
            run_started=True,
        ),
        WorkflowCommand(destination_stage="verify"),
    )

    assert graph.reference == "ctower.trust-spine-four-stage@1"
    assert decision.accepted is True
    assert decision.activity_class is ActivityClass.VERIFICATION


def test_workflow_implementation_contains_no_fixture_stage_name_literals() -> None:
    forbidden = {"capture", "frame", "verify", "close"}
    strings = {
        node.value
        for path in (ROOT / "packages/ctower-kernel/src/ctower_kernel/workflow").glob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert strings.isdisjoint(forbidden)


def test_mapping_parser_rejects_unversioned_failure_route_metadata() -> None:
    payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    payload["failure_routes"] = [
        {"from": "frame", "failure_class_ref": "unversioned", "to": "capture"}
    ]

    with pytest.raises(ValueError, match="failure route class must be versioned"):
        WorkflowGraph.from_mapping(payload)


def test_mapping_parser_rejects_missing_or_unknown_initial_stage() -> None:
    payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    missing = dict(payload)
    del missing["initial_stage"]
    unknown = {**payload, "initial_stage": "unknown"}

    with pytest.raises(ValueError, match="payload fields"):
        WorkflowGraph.from_mapping(missing)
    with pytest.raises(ValueError, match="initial stage must reference one declared stage"):
        WorkflowGraph.from_mapping(unknown)
