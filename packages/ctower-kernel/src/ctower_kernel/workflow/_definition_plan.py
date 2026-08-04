"""Gates 2 and 3: resolve one authored source revision and normalize its payload.

Gate 2 applies exactly the matching project overlay, proves every declared edge
restates its source stage's normalized slot set, and derives the graph endpoints.
Gate 3 renders the normalized `ctower.workflow/v1` payload and refuses — with the
missing fact and its stage named — rather than supplying any default.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ctower_kernel.workflow._definition_model import (
    EvidenceSlot,
    ProjectOverlay,
    SkipSet,
    StageDefinition,
    TransitionDefinition,
    WorkflowDefinition,
    WorkflowDefinitionRefusedError,
)
from ctower_kernel.workflow._graph import ActivityClass

__all__ = [
    "ResolvedStage",
    "ResolvedWorkflow",
    "WorkflowResolution",
    "normalized_payload",
    "resolve_definition",
]

_NORMALIZED_SCHEMA = "ctower.workflow/v1"


@dataclass(frozen=True, slots=True)
class ResolvedStage:
    """One stage after exactly the applicable project overlay is applied."""

    name: str
    owner: str
    group: str | None
    required_evidence_slots: tuple[EvidenceSlot, ...]
    signing_slot: str | None
    gate: str | None
    skip: SkipSet | None
    failure_routes: tuple[tuple[str, str], ...]
    terminal: bool

    @property
    def slot_keys(self) -> tuple[str, ...]:
        """Return the normalized required slot keys in base-then-overlay order."""

        return tuple(slot.key for slot in self.required_evidence_slots)


@dataclass(frozen=True, slots=True)
class ResolvedWorkflow:
    """One authored revision resolved for exactly one project, or for the base."""

    key: str
    revision: int
    project: str | None
    stage_groups: tuple[str, ...]
    initial_stage: str
    stages: tuple[ResolvedStage, ...]
    transitions: tuple[TransitionDefinition, ...]

    def stage(self, name: str) -> ResolvedStage | None:
        """Return one resolved stage by its authored name."""

        return next((item for item in self.stages if item.name == name), None)


@dataclass(frozen=True, slots=True)
class WorkflowResolution:
    """The exact pinned facts this source deliberately never authors."""

    activity_classes: Mapping[str, ActivityClass]
    transition_predicates: Mapping[tuple[str, str], str]
    failure_classes: Mapping[str, str]
    input_contract: str
    terminal_contract: str
    execution_policy_ref: str
    gate_policy_ref: str
    status: str
    note: str


def resolve_definition(
    definition: WorkflowDefinition,
    *,
    project: str | None = None,
) -> ResolvedWorkflow:
    """Apply one project overlay and derive the graph, refusing by name at gate 2."""

    overlay = None if project is None else definition.overlay(project)
    _check_overlay(definition, overlay)
    outgoing = {edge.source for edge in definition.transitions}
    stages = tuple(_resolved_stage(stage, overlay, outgoing) for stage in definition.stages)
    _check_edges(definition)
    _check_routes(definition, stages)
    _check_endpoints(definition, stages)
    initial = _initial_stage(definition, stages)
    _check_reachable(definition, stages, initial)
    return ResolvedWorkflow(
        key=definition.name,
        revision=definition.revision,
        project=project,
        stage_groups=definition.stage_groups,
        initial_stage=initial,
        stages=stages,
        transitions=definition.transitions,
    )


def normalized_payload(
    resolved: ResolvedWorkflow,
    resolution: WorkflowResolution,
) -> dict[str, object]:
    """Render the normalized `ctower.workflow/v1` payload without any default."""

    return {
        "schema": _NORMALIZED_SCHEMA,
        "status": resolution.status,
        "key": resolved.key,
        "revision": resolved.revision,
        "initial_stage": resolved.initial_stage,
        "input_contract": resolution.input_contract,
        "terminal_contract": resolution.terminal_contract,
        "policy_refs": {
            "execution": resolution.execution_policy_ref,
            "gates": resolution.gate_policy_ref,
        },
        "stages": [_normalized_stage(stage, resolution) for stage in resolved.stages],
        "transitions": [_normalized_edge(edge, resolution) for edge in resolved.transitions],
        "failure_routes": [
            route for stage in resolved.stages for route in _normalized_routes(stage, resolution)
        ],
        "note": resolution.note,
    }


def _resolved_stage(
    stage: StageDefinition,
    overlay: ProjectOverlay | None,
    outgoing: set[str],
) -> ResolvedStage:
    additions = () if overlay is None else _overlay_slots(overlay, stage.name)
    return ResolvedStage(
        name=stage.name,
        owner=stage.owner,
        group=stage.group,
        required_evidence_slots=stage.evidence + additions,
        signing_slot=stage.signs,
        gate=stage.gate,
        skip=stage.skip,
        failure_routes=stage.failure_routes,
        terminal=stage.name not in outgoing,
    )


def _overlay_slots(overlay: ProjectOverlay, name: str) -> tuple[EvidenceSlot, ...]:
    return next((slots for stage, slots in overlay.stages if stage == name), ())


def _check_overlay(definition: WorkflowDefinition, overlay: ProjectOverlay | None) -> None:
    if overlay is None:
        return
    base = {stage.name: set(stage.slot_keys) for stage in definition.stages}
    for stage_name, slots in overlay.stages:
        declared = base.get(stage_name)
        if declared is None:
            raise WorkflowDefinitionRefusedError("overlay.unknown-stage", stage_name)
        for slot in slots:
            if slot.key in declared:
                raise WorkflowDefinitionRefusedError(
                    "overlay.slot-collision", slot.key, stage=stage_name
                )


def _check_edges(definition: WorkflowDefinition) -> None:
    """Prove the authored restatement against the base list every project shares.

    One authored `requires` serves every project, so it restates the base slot set.
    Each project's own edge requirement set is derived from its resolved stage, never
    re-authored, which is why `ResolvedStage.slot_keys` is the whole answer for an edge.
    """

    slots = {stage.name: stage.slot_keys for stage in definition.stages}
    seen: set[tuple[str, str]] = set()
    for edge in definition.transitions:
        for name in (edge.source, edge.destination):
            if name not in slots:
                raise WorkflowDefinitionRefusedError("graph.unknown-stage", name)
        if (edge.source, edge.destination) in seen:
            raise WorkflowDefinitionRefusedError(
                "graph.duplicate-edge", edge.destination, stage=edge.source
            )
        seen.add((edge.source, edge.destination))
        if edge.requires != slots[edge.source]:
            raise WorkflowDefinitionRefusedError(
                "transition.divergent-requires", edge.destination, stage=edge.source
            )


def _check_routes(definition: WorkflowDefinition, stages: tuple[ResolvedStage, ...]) -> None:
    names = {stage.name for stage in stages}
    for stage in definition.stages:
        for reason, target in stage.failure_routes:
            if target not in names:
                raise WorkflowDefinitionRefusedError(
                    "graph.unknown-route-target", reason, stage=stage.name
                )


def _check_endpoints(definition: WorkflowDefinition, stages: tuple[ResolvedStage, ...]) -> None:
    if not any(stage.terminal for stage in stages):
        raise WorkflowDefinitionRefusedError("graph.no-terminal-stage", definition.name)


def _initial_stage(definition: WorkflowDefinition, stages: tuple[ResolvedStage, ...]) -> str:
    incoming = {edge.destination for edge in definition.transitions}
    entries = tuple(stage.name for stage in stages if stage.name not in incoming)
    if len(entries) != 1:
        raise WorkflowDefinitionRefusedError("graph.entry-stage", ",".join(entries) or "none")
    return entries[0]


def _check_reachable(
    definition: WorkflowDefinition,
    stages: tuple[ResolvedStage, ...],
    initial: str,
) -> None:
    reached = {initial}
    pending = [initial]
    while pending:
        current = pending.pop()
        for edge in definition.transitions:
            if edge.source == current and edge.destination not in reached:
                reached.add(edge.destination)
                pending.append(edge.destination)
    for stage in stages:
        if stage.name not in reached:
            raise WorkflowDefinitionRefusedError("graph.unreachable-stage", stage.name)


def _normalized_stage(stage: ResolvedStage, resolution: WorkflowResolution) -> dict[str, object]:
    activity = resolution.activity_classes.get(stage.name)
    if activity is None:
        raise WorkflowDefinitionRefusedError("payload.activity-class", stage.name, stage=stage.name)
    if stage.signing_slot is None:
        raise WorkflowDefinitionRefusedError("payload.signing-slot", stage.name, stage=stage.name)
    return {"key": stage.name, "activity_class": activity.value}


def _normalized_edge(
    edge: TransitionDefinition,
    resolution: WorkflowResolution,
) -> dict[str, object]:
    predicate = resolution.transition_predicates.get((edge.source, edge.destination))
    if predicate is None:
        raise WorkflowDefinitionRefusedError(
            "payload.transition-predicate", edge.destination, stage=edge.source
        )
    return {"from": edge.source, "to": edge.destination, "predicate_ref": predicate}


def _normalized_routes(
    stage: ResolvedStage,
    resolution: WorkflowResolution,
) -> list[dict[str, object]]:
    routes: list[dict[str, object]] = []
    for reason, target in stage.failure_routes:
        failure_class = resolution.failure_classes.get(reason)
        if failure_class is None:
            raise WorkflowDefinitionRefusedError("payload.failure-class", reason, stage=stage.name)
        routes.append({"from": stage.name, "failure_class_ref": failure_class, "to": target})
    return routes
