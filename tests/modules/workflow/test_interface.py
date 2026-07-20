"""Public Workflow Interface tracer tests."""

from __future__ import annotations

import ast
import json
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
)

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()


def _graph(*, key: str = "fixture.generic", revision: int = 1) -> WorkflowGraph:
    return WorkflowGraph(
        key=key,
        revision=revision,
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
    workflow = Workflow((graph,))

    accepted = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.ready@1"}),
        ),
        WorkflowCommand(destination_stage="beta"),
    )
    undeclared = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset({"predicate.proved@1"}),
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
        ),
        WorkflowCommand(destination_stage="beta"),
    )
    missing_predicate = workflow.evaluate(
        WorkflowContextSnapshot(
            workflow_ref="fixture.generic@1",
            current_stage="alpha",
            satisfied_predicates=frozenset(),
        ),
        WorkflowCommand(destination_stage="beta"),
    )

    assert unknown_version.accepted is False
    assert unknown_version.reason == "workflow-version-unknown"
    assert missing_predicate.accepted is False
    assert missing_predicate.reason == "predicate-unsatisfied"


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
