"""Small public Interface for the record-backed landing-boundary check.

The check is a pure reader.  It accepts the record's answer for exactly one change,
resolves that change's ticket, its pinned Workflow graph, and the candidate digest its
head revision resolves to, then reports each fact of the landing-boundary predecessor
set separately.  It writes no authoritative state, mints no Evidence, fills no slot, and
passes no gate, so its verdict is never itself proof.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import ValidationError

from ctower_kernel.workflow import WorkflowGraph
from tools.landing_boundary.boundary import landing_boundary_predecessors
from tools.landing_boundary.facts import stage_fact, unresolved_stage_fact
from tools.landing_boundary.models import (
    ChangeIdentity,
    LandingBoundaryError,
    RecordSnapshot,
    StageRecord,
)
from tools.landing_boundary.policy import VerdictTierPolicy
from tools.landing_boundary.report import FactStatus, LandingBoundaryReport, StageFact

__all__ = ["evaluate_landing_boundary", "read_record_snapshot", "refused_report"]

_SCHEMA: Final = "ctower.landing-boundary-report/v1"


def read_record_snapshot(path: Path) -> RecordSnapshot:
    """Parse the record's answer strictly; an unreadable answer is not an answer."""

    try:
        return RecordSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        raise LandingBoundaryError(f"unreadable record snapshot: {error}") from error
    except ValidationError as error:
        raise LandingBoundaryError(
            f"record snapshot violates its typed contract: {_bounded(error)}"
        ) from error


def evaluate_landing_boundary(
    snapshot: RecordSnapshot, change: ChangeIdentity, policy: VerdictTierPolicy
) -> LandingBoundaryReport:
    """Report every landing-boundary fact for one change, green only when all pass."""

    candidate_digest, refusal = _resolve_change(snapshot, change)
    stage_keys: tuple[str, ...] = ()
    if refusal is None:
        stage_keys, refusal = _resolve_predecessors(snapshot)
    facts = (
        _stage_facts(snapshot.stages, stage_keys, candidate_digest, policy)
        if candidate_digest is not None
        else ()
    )
    binding = snapshot.binding
    workflow = snapshot.workflow
    return _report(
        change=change,
        ticket_id=binding.ticket_id if binding is not None else None,
        project_key=binding.project_key if binding is not None else None,
        candidate_digest=candidate_digest,
        landing_boundary_stage=workflow.landing_boundary_stage if workflow is not None else None,
        facts=facts,
        refusals=_refusals(refusal, facts),
    )


def refused_report(
    change: ChangeIdentity, refusal: str, detail: str | None = None
) -> LandingBoundaryReport:
    """Refuse before any fact could be read, naming why the record was not consulted."""

    return _report(
        change=change,
        ticket_id=None,
        project_key=None,
        candidate_digest=None,
        landing_boundary_stage=None,
        facts=(),
        refusals=(refusal,),
        detail=detail,
    )


def _resolve_change(
    snapshot: RecordSnapshot, change: ChangeIdentity
) -> tuple[str | None, str | None]:
    if snapshot.change != change:
        return None, "record-answers-a-different-change"
    if snapshot.availability == "unavailable":
        return None, "record-unavailable"
    binding = snapshot.binding
    if binding is None:
        return None, "change-not-bound-to-ticket"
    if binding.candidate_digest is None:
        return None, "candidate-digest-unresolved"
    return binding.candidate_digest, None


def _resolve_predecessors(snapshot: RecordSnapshot) -> tuple[tuple[str, ...], str | None]:
    workflow = snapshot.workflow
    if workflow is None:
        return (), "pinned-workflow-unresolved"
    try:
        graph = WorkflowGraph.from_mapping(workflow.graph)
    except (TypeError, ValueError):
        return (), "pinned-workflow-invalid"
    if graph.digest != workflow.graph_digest:
        return (), "pinned-workflow-digest-mismatch"
    if workflow.landing_boundary_stage is None:
        return (), "landing-boundary-undeclared"
    try:
        return landing_boundary_predecessors(graph, workflow.landing_boundary_stage), None
    except LandingBoundaryError:
        return (), "landing-boundary-unreachable"


def _stage_facts(
    stages: tuple[StageRecord, ...],
    stage_keys: tuple[str, ...],
    candidate_digest: str,
    policy: VerdictTierPolicy,
) -> tuple[StageFact, ...]:
    recorded = {stage.stage_key: stage for stage in stages}
    return tuple(
        stage_fact(recorded[key], candidate_digest=candidate_digest, policy=policy)
        if key in recorded
        else unresolved_stage_fact(key)
        for key in stage_keys
    )


def _refusals(refusal: str | None, facts: tuple[StageFact, ...]) -> tuple[str, ...]:
    named = tuple(fact.refusal for fact in facts if fact.refusal is not None)
    return named if refusal is None else (refusal, *named)


def _report(
    *,
    change: ChangeIdentity,
    ticket_id: str | None,
    project_key: str | None,
    candidate_digest: str | None,
    landing_boundary_stage: str | None,
    facts: tuple[StageFact, ...],
    refusals: tuple[str, ...],
    detail: str | None = None,
) -> LandingBoundaryReport:
    green = not refusals and all(fact.status is FactStatus.PASSING for fact in facts)
    return LandingBoundaryReport(
        schema=_SCHEMA,
        verdict="pass" if green else "refused",
        change=change,
        ticket_id=ticket_id,
        project_key=project_key,
        candidate_digest=candidate_digest,
        landing_boundary_stage=landing_boundary_stage,
        facts=facts,
        refusals=refusals,
        detail=detail,
    )


def _bounded(value: object) -> str:
    return " ".join(str(value).split())[:1000]
