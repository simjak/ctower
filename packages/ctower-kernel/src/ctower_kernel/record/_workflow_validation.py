"""Validation shared by the enriched workflow transition payload."""

from __future__ import annotations

import re

_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")


def validate_workflow_provenance(operation: str, source_stage: str, evaluation_ref: str) -> None:
    if source_stage and _STABLE_KEY.fullmatch(source_stage) is None:
        raise ValueError("workflow source stage must be stable or empty")
    if operation == "transition" and (not source_stage or not evaluation_ref):
        raise ValueError("workflow transitions require source stage and evaluation reference")
