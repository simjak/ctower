"""Immutable authored Workflow Definition source model and its named refusal."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AssertionValue",
    "EvidenceSlot",
    "ProjectOverlay",
    "SkipSet",
    "StageDefinition",
    "TransitionDefinition",
    "WorkflowDefinition",
    "WorkflowDefinitionRefusedError",
]

type AssertionValue = str | bool | tuple[int, ...]


class WorkflowDefinitionRefusedError(ValueError):
    """A refusal that always names the offending member, key, or unresolved fact."""

    def __init__(self, rule: str, name: str, *, stage: str | None = None) -> None:
        self.rule = rule
        self.name = name
        self.stage = stage
        located = "" if stage is None else f" in stage {stage}"
        super().__init__(f"{rule} refuses {name}{located}")


@dataclass(frozen=True, slots=True)
class EvidenceSlot:
    """One required exit-evidence assertion narrowing a layer-4 definition."""

    key: str
    assertions: tuple[tuple[str, AssertionValue], ...]


@dataclass(frozen=True, slots=True)
class SkipSet:
    """The alternative slot set that replaces the ordinary set on a skip."""

    predicate: str
    evidence: tuple[EvidenceSlot, ...]
    signs: str | None


@dataclass(frozen=True, slots=True)
class StageDefinition:
    """One authored stage: its responsibility and its own exit-evidence list."""

    name: str
    owner: str
    evidence: tuple[EvidenceSlot, ...]
    group: str | None
    signs: str | None
    gate: str | None
    skip: SkipSet | None
    failure_routes: tuple[tuple[str, str], ...]

    @property
    def slot_keys(self) -> tuple[str, ...]:
        """Return the authored ordinary slot keys in authored order."""

        return tuple(slot.key for slot in self.evidence)


@dataclass(frozen=True, slots=True)
class TransitionDefinition:
    """One directed edge restating the normalized slot set of its source stage."""

    source: str
    destination: str
    requires: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectOverlay:
    """Exactly the additions one layer-2 project makes to the base definition."""

    project: str
    stages: tuple[tuple[str, tuple[EvidenceSlot, ...]], ...]


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """One immutable authored `ctower.workflow-definition/v1` revision."""

    name: str
    company: str
    revision: int
    signed_by: str
    stage_groups: tuple[str, ...]
    stages: tuple[StageDefinition, ...]
    transitions: tuple[TransitionDefinition, ...]
    overlays: tuple[ProjectOverlay, ...]

    @property
    def reference(self) -> str:
        """Return the immutable component reference this revision publishes as."""

        return f"{self.name}@{self.revision}"

    def overlay(self, project: str) -> ProjectOverlay | None:
        """Return exactly the matching project overlay, or None for the base."""

        return next((item for item in self.overlays if item.project == project), None)
