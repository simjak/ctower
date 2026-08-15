"""Validation shared by the enriched workflow transition payload."""

from __future__ import annotations

import re
from collections.abc import Mapping

_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")


def validate_workflow_provenance(
    operation: str,
    source_stage: str,
    evaluation_ref: str,
    *,
    require_transition: bool = False,
) -> None:
    if source_stage and _STABLE_KEY.fullmatch(source_stage) is None:
        raise ValueError("workflow source stage must be stable or empty")
    if (
        require_transition
        and operation == "transition"
        and (not source_stage or not evaluation_ref)
    ):
        raise ValueError("workflow transitions require source stage and evaluation reference")


def workflow_payload_for_read(payload: Mapping[str, object]) -> dict[str, object]:
    """Supply honest empty provenance for pre-enrichment workflow events."""

    normalized = dict(payload)
    normalized.setdefault("source_stage", "")
    normalized.setdefault("evaluation_ref", "")
    return normalized
