"""Derive the landing-boundary predecessor set from one pinned Workflow graph.

The set is every stage the graph places before the stage carrying the landing boundary.
It is computed from the pinned graph's own edges, so a package that renames a stage, or
a non-engineering Workflow that declares a different graph, changes the reported set
with no change here.  No stage key, group key, or evidence kind appears in this module.
"""

from __future__ import annotations

from ctower_kernel.workflow import WorkflowGraph
from tools.landing_boundary.models import LandingBoundaryError

__all__ = ["landing_boundary_predecessors"]


def landing_boundary_predecessors(
    graph: WorkflowGraph, landing_boundary_stage: str
) -> tuple[str, ...]:
    """Return every stage the pinned graph places before the landing boundary."""

    declared = tuple(stage.key for stage in graph.stages)
    if landing_boundary_stage not in declared:
        raise LandingBoundaryError("landing-boundary stage is absent from the pinned graph")
    predecessors = _ancestors(graph, landing_boundary_stage)
    if landing_boundary_stage != graph.initial_stage and graph.initial_stage not in predecessors:
        raise LandingBoundaryError(
            "pinned graph places no path from its initial stage to the landing boundary"
        )
    return tuple(key for key in declared if key in predecessors)


def _ancestors(graph: WorkflowGraph, target: str) -> frozenset[str]:
    incoming: dict[str, list[str]] = {}
    for edge in graph.transitions:
        incoming.setdefault(edge.destination, []).append(edge.source)
    reached: set[str] = set()
    frontier = [target]
    while frontier:
        for source in incoming.get(frontier.pop(), ()):
            if source not in reached:
                reached.add(source)
                frontier.append(source)
    reached.discard(target)
    return frozenset(reached)
