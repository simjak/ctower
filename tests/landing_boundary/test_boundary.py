"""The predecessor set comes from the pinned graph, not from a list in the check."""

from __future__ import annotations

import pytest

from ctower_kernel.workflow import WorkflowGraph
from tools.landing_boundary.boundary import landing_boundary_predecessors
from tools.landing_boundary.models import LandingBoundaryError

from . import support

__all__: tuple[str, ...] = ()


def _graph(stage_keys: tuple[str, ...]) -> WorkflowGraph:
    return WorkflowGraph.from_mapping(support.graph_payload(stage_keys))


def test_linear_graph_reports_every_stage_before_the_boundary() -> None:
    graph = _graph(support.SOFTWARE_FACTORY_STAGES)

    assert landing_boundary_predecessors(graph, support.LANDING_STAGE) == (
        "intake",
        "think",
        "plan",
        "design",
        "implement",
        "local-verification-qa",
        "risk-derived-review",
        "documentation",
        "release-preflight",
    )


def test_renamed_stages_rename_the_derived_set_with_no_check_change() -> None:
    renamed = tuple(f"phase-{index}" for index in range(4))
    graph = _graph(renamed)

    assert landing_boundary_predecessors(graph, "phase-3") == ("phase-0", "phase-1", "phase-2")


def test_a_different_pinned_workflow_reports_a_different_set() -> None:
    graph = _graph(("capture", "frame", "verify", "close"))

    assert landing_boundary_predecessors(graph, "close") == ("capture", "frame", "verify")


def test_a_boundary_on_the_initial_stage_has_an_empty_predecessor_set() -> None:
    graph = _graph(support.SOFTWARE_FACTORY_STAGES)

    assert landing_boundary_predecessors(graph, "intake") == ()


def test_the_set_follows_declaration_order_of_the_pinned_graph() -> None:
    graph = _graph(("gamma", "alpha", "beta"))

    assert landing_boundary_predecessors(graph, "beta") == ("gamma", "alpha")


def test_a_boundary_absent_from_the_graph_refuses() -> None:
    graph = _graph(support.SOFTWARE_FACTORY_STAGES)

    with pytest.raises(LandingBoundaryError, match="absent from the pinned graph"):
        landing_boundary_predecessors(graph, "no-such-stage")


def test_a_boundary_unreachable_from_the_initial_stage_refuses() -> None:
    payload = support.graph_payload(("intake", "think"))
    payload["stages"] = [*payload["stages"], {"key": "orphan", "activity_class": "work"}]
    graph = WorkflowGraph.from_mapping(payload)

    with pytest.raises(LandingBoundaryError, match="no path from its initial stage"):
        landing_boundary_predecessors(graph, "orphan")


def test_a_cycle_through_the_boundary_does_not_make_it_its_own_predecessor() -> None:
    payload = support.graph_payload(("intake", "think", "merge"))
    payload["transitions"] = [
        *payload["transitions"],
        {"from": "merge", "to": "think", "predicate_ref": "entry.ready@1"},
    ]
    graph = WorkflowGraph.from_mapping(payload)

    assert landing_boundary_predecessors(graph, "merge") == ("intake", "think")
