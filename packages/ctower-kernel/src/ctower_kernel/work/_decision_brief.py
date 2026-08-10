"""Pure Request-record to operator decision-brief projection."""

from __future__ import annotations

import json
from uuid import UUID

from ctower_kernel.work._request_types import (
    DecisionBrief,
    DecisionBriefChoice,
    DecisionBriefSelection,
)

__all__ = ["OPERATOR_DECISION_BLOCKER", "decision_brief"]

OPERATOR_DECISION_BLOCKER = "operator-decision-required"

_ELI = "This Request needs your decision before work can continue."
_CHOICES = (
    DecisionBriefChoice("A", "Continue this Request as recorded.", 10),
    DecisionBriefChoice("B", "Keep this Request blocked for clarification.", 8),
    DecisionBriefChoice("C", "Stop this Request without starting new work.", 10),
)
_SAFE_DEFAULT = DecisionBriefSelection(
    "B", "Silence keeps the Request blocked and causes no effect."
)
_RECOMMENDATIONS = {
    "ACCEPTED": DecisionBriefSelection("A", "This Request already passed triage."),
    "DUPLICATE": DecisionBriefSelection("C", "This Request is recorded as a duplicate."),
    "REJECTED": DecisionBriefSelection("C", "This Request is recorded as rejected."),
    "UNTRIAGED": DecisionBriefSelection("B", "This Request has not passed triage yet."),
}


def decision_brief(
    *,
    content: str,
    reference: str,
    triage: str,
    ruling_id: UUID | None,
) -> DecisionBrief:
    """Build the closed brief shape without accepting caller render facts."""

    recommendation = _RECOMMENDATIONS[triage]
    status = "open" if ruling_id is None else "answered"
    lines = [
        f"Decision needed ({reference})",
        "",
        f"ELI: {_ELI}",
        f"Origin: {json.dumps(content, ensure_ascii=False)}",
        *(
            f"Choice {choice.key}: {choice.outcome} Completeness: {choice.completeness}/10."
            for choice in _CHOICES
        ),
        f"Recommendation: {recommendation.choice_key}. {recommendation.reason}",
        f"Safe default: {_SAFE_DEFAULT.choice_key}. {_SAFE_DEFAULT.reason}",
    ]
    if ruling_id is not None:
        lines.append(f"Answer: Ruling {ruling_id}.")
    return DecisionBrief(
        eli=_ELI,
        origin_quote=content,
        choices=_CHOICES,
        recommendation=recommendation,
        safe_default=_SAFE_DEFAULT,
        rendered="\n".join(lines),
        status=status,
        ruling_id=ruling_id,
    )
