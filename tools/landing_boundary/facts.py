"""Decide one stage's fact from the record's resolved required slot set.

The same rules apply to every stage of the predecessor set, whatever it carries: a slot
is met only when it is filled, valid, and bound to the candidate digest the change's
head revision resolves to, produced by someone other than the identity it verifies, and
— where it binds verdicts — signed off at or above the tier its class owes.  Nothing
here branches on which stage, group, or evidence kind is being read.
"""

from __future__ import annotations

from tools.landing_boundary.models import SlotRecord, StageRecord, VerdictRecord
from tools.landing_boundary.policy import VerdictTierPolicy
from tools.landing_boundary.report import FactStatus, FindingReason, SlotFinding, StageFact

__all__ = ["stage_fact", "unresolved_stage_fact"]

_MET_STATES = {"filled"}
_MET_DISPOSITION = "signed-off"


def stage_fact(
    record: StageRecord, *, candidate_digest: str, policy: VerdictTierPolicy
) -> StageFact:
    """Fold every required slot of one stage instance into a single reported fact."""

    if record.resolution == "unknown":
        return unresolved_stage_fact(record.stage_key)
    findings = tuple(
        finding
        for slot in record.required_slots
        for finding in _slot_findings(slot, candidate_digest=candidate_digest, policy=policy)
    )
    return StageFact.resolve(record.stage_key, findings)


def unresolved_stage_fact(stage_key: str) -> StageFact:
    """Report a stage the record could not resolve at all as unknown, never as passing."""

    return StageFact(
        stage_key=stage_key,
        status=FactStatus.STATE_UNKNOWN,
        refusal=f"missing-{stage_key}-evidence",
        findings=(SlotFinding(slot_key=None, reason=FindingReason.STAGE_UNRESOLVED, detail=None),),
    )


def _slot_findings(
    slot: SlotRecord, *, candidate_digest: str, policy: VerdictTierPolicy
) -> tuple[SlotFinding, ...]:
    if slot.state == "unknown":
        return (_finding(slot, FindingReason.SLOT_STATE_UNKNOWN),)
    if slot.state not in _MET_STATES:
        return (_finding(slot, FindingReason.SLOT_UNFILLED),)
    findings = [*_currency_findings(slot, candidate_digest)]
    if slot.self_reported:
        findings.append(_finding(slot, FindingReason.SLOT_SELF_REPORTED))
    findings.extend(
        finding for verdict in slot.verdicts for finding in _verdict_findings(slot, verdict, policy)
    )
    return tuple(findings)


def _currency_findings(slot: SlotRecord, candidate_digest: str) -> tuple[SlotFinding, ...]:
    findings: list[SlotFinding] = []
    if slot.validity == "unknown":
        findings.append(_finding(slot, FindingReason.SLOT_VALIDITY_UNKNOWN))
    elif slot.validity != "current":
        findings.append(_finding(slot, FindingReason.SLOT_NOT_CURRENT, slot.validity))
    if slot.bound_candidate_digest is None:
        findings.append(_finding(slot, FindingReason.SLOT_CANDIDATE_UNBOUND))
    elif slot.bound_candidate_digest != candidate_digest:
        findings.append(
            _finding(slot, FindingReason.SLOT_SUPERSEDED_CANDIDATE, slot.bound_candidate_digest)
        )
    return tuple(findings)


def _verdict_findings(
    slot: SlotRecord, verdict: VerdictRecord, policy: VerdictTierPolicy
) -> tuple[SlotFinding, ...]:
    findings: list[SlotFinding] = []
    if verdict.disposition == "unknown":
        findings.append(
            _finding(slot, FindingReason.VERDICT_DISPOSITION_UNKNOWN, verdict.verdict_id)
        )
    elif verdict.disposition != _MET_DISPOSITION:
        findings.append(_finding(slot, FindingReason.VERDICT_NOT_SIGNED_OFF, verdict.verdict_id))
    if verdict.self_reported:
        findings.append(_finding(slot, FindingReason.VERDICT_SELF_REPORTED, verdict.verdict_id))
    if policy.is_below_floor(verdict.verdict_class, verdict.signing_model):
        findings.append(
            _finding(
                slot,
                FindingReason.VERDICT_TIER_BELOW_POLICY,
                f"{verdict.verdict_id} signed by {verdict.signing_model}",
            )
        )
    return tuple(findings)


def _finding(slot: SlotRecord, reason: FindingReason, detail: str | None = None) -> SlotFinding:
    return SlotFinding(slot_key=slot.slot_key, reason=reason, detail=detail)
