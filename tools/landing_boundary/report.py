"""The check's verdict values and its deterministic rendering.

Each fact of the landing-boundary predecessor set is reported separately, named by its
stage and its unmet slot.  ``STATE_UNKNOWN`` is a failure rather than a caveat, so a
report is green only when every fact passes.  Refusal names are composed from the stage
keys the pinned graph supplies; no stage key, group key, or evidence kind is written
here, so a renamed stage renames its refusal with no change to this module.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from tools.landing_boundary.models import ChangeIdentity

__all__ = [
    "FactStatus",
    "FindingReason",
    "LandingBoundaryReport",
    "SlotFinding",
    "StageFact",
    "render_report",
    "status_for",
]


class FactStatus(StrEnum):
    """The disposition of one stage's fact at the landing boundary."""

    PASSING = "pass"
    FLAGGED = "flagged"
    FAIL = "fail"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class FindingReason(StrEnum):
    """Why one required slot does not carry current proof."""

    STAGE_UNRESOLVED = "stage-unresolved"
    SLOT_UNFILLED = "slot-unfilled"
    SLOT_STATE_UNKNOWN = "slot-state-unknown"
    SLOT_NOT_CURRENT = "slot-not-current"
    SLOT_VALIDITY_UNKNOWN = "slot-validity-unknown"
    SLOT_CANDIDATE_UNBOUND = "slot-candidate-unbound"
    SLOT_SUPERSEDED_CANDIDATE = "slot-superseded-candidate"
    SLOT_SELF_REPORTED = "slot-self-reported"
    VERDICT_NOT_SIGNED_OFF = "verdict-not-signed-off"
    VERDICT_DISPOSITION_UNKNOWN = "verdict-disposition-unknown"
    VERDICT_SELF_REPORTED = "verdict-self-reported"
    VERDICT_TIER_BELOW_POLICY = "verdict-tier-below-policy"


_REASON_STATUS = {
    FindingReason.STAGE_UNRESOLVED: FactStatus.STATE_UNKNOWN,
    FindingReason.SLOT_UNFILLED: FactStatus.FAIL,
    FindingReason.SLOT_STATE_UNKNOWN: FactStatus.STATE_UNKNOWN,
    FindingReason.SLOT_NOT_CURRENT: FactStatus.FAIL,
    FindingReason.SLOT_VALIDITY_UNKNOWN: FactStatus.STATE_UNKNOWN,
    FindingReason.SLOT_CANDIDATE_UNBOUND: FactStatus.STATE_UNKNOWN,
    FindingReason.SLOT_SUPERSEDED_CANDIDATE: FactStatus.FAIL,
    FindingReason.SLOT_SELF_REPORTED: FactStatus.FAIL,
    FindingReason.VERDICT_NOT_SIGNED_OFF: FactStatus.FAIL,
    FindingReason.VERDICT_DISPOSITION_UNKNOWN: FactStatus.STATE_UNKNOWN,
    FindingReason.VERDICT_SELF_REPORTED: FactStatus.FAIL,
    FindingReason.VERDICT_TIER_BELOW_POLICY: FactStatus.FLAGGED,
}
_STATUS_PRECEDENCE = (FactStatus.STATE_UNKNOWN, FactStatus.FAIL, FactStatus.FLAGGED)


def status_for(reason: FindingReason) -> FactStatus:
    """Return the disposition one finding reason forces on its stage's fact."""

    return _REASON_STATUS[reason]


class _Value(BaseModel):
    """Strict immutable base for every reported value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SlotFinding(_Value):
    """One named reason a stage's fact is not passing."""

    slot_key: str | None
    reason: FindingReason
    detail: str | None


class StageFact(_Value):
    """One member of the landing-boundary predecessor set, reported separately."""

    stage_key: str
    status: FactStatus
    refusal: str | None
    findings: tuple[SlotFinding, ...]

    @classmethod
    def resolve(cls, stage_key: str, findings: tuple[SlotFinding, ...]) -> StageFact:
        """Fold findings into one disposition and its derived refusal name."""

        status = _worst_status(findings)
        return cls(
            stage_key=stage_key,
            status=status,
            refusal=_refusal_for(stage_key, status),
            findings=findings,
        )


class LandingBoundaryReport(_Value):
    """The whole check verdict: every fact, and every unmet fact by its stable name."""

    schema_: Literal["ctower.landing-boundary-report/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    verdict: Literal["pass", "refused"]
    change: ChangeIdentity
    ticket_id: str | None
    project_key: str | None
    candidate_digest: str | None
    landing_boundary_stage: str | None
    facts: Annotated[tuple[StageFact, ...], Field(max_length=256)]
    refusals: Annotated[tuple[str, ...], Field(max_length=256)]
    detail: str | None


def render_report(report: LandingBoundaryReport) -> str:
    """Render one deterministic terminal-safe report body."""

    passing = sum(1 for fact in report.facts if fact.status is FactStatus.PASSING)
    lines = [
        f"landing boundary: {report.verdict.upper()}",
        f"change: {report.change.repository}"
        f" pull-request={report.change.pull_request_reference}"
        f" head={report.change.head_revision}",
        f"ticket: {report.ticket_id or 'STATE_UNKNOWN'}"
        f" project={report.project_key or 'STATE_UNKNOWN'}"
        f" candidate={report.candidate_digest or 'STATE_UNKNOWN'}",
        f"landing-boundary stage: {report.landing_boundary_stage or 'STATE_UNKNOWN'}",
        f"facts: {passing}/{len(report.facts)} pass",
    ]
    lines.extend(_fact_lines(report))
    if report.detail is not None:
        lines.append(f"detail: {report.detail}")
    lines.extend(f"refused: {name}" for name in report.refusals)
    return "\n".join(lines) + "\n"


def _fact_lines(report: LandingBoundaryReport) -> list[str]:
    lines: list[str] = []
    for fact in report.facts:
        lines.append(f"  {fact.status.value:<14} {fact.stage_key}")
        lines.extend(
            f"      {finding.slot_key or '-'}: {finding.reason.value}"
            f"{'' if finding.detail is None else f' ({finding.detail})'}"
            for finding in fact.findings
        )
    return lines


def _worst_status(findings: tuple[SlotFinding, ...]) -> FactStatus:
    statuses = {status_for(finding.reason) for finding in findings}
    return next(
        (status for status in _STATUS_PRECEDENCE if status in statuses),
        FactStatus.PASSING,
    )


def _refusal_for(stage_key: str, status: FactStatus) -> str | None:
    if status is FactStatus.PASSING:
        return None
    if status is FactStatus.FLAGGED:
        return f"flagged-{stage_key}-verdict-tier"
    return f"missing-{stage_key}-evidence"
