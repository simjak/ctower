"""Compact Project Delivery is strict, proof-aware, and read-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]


def test_compact_row_exposes_proof_coverage_without_writable_status_or_percentage() -> None:
    validator = _validator()
    row: dict[str, object] = {
        "checkpoint_key": "I1.7",
        "checkpoint_label": "Development dogfood cutover",
        "headline_state": "blocked",
        "underlying_maturity": "verified",
        "outcome": "ctower owns reconstructible engineering work",
        "accountable_owner": "operator",
        "criteria": {"proven": 5, "declared": 6},
        "source_watermark": 27,
        "projection_watermark": 27,
        "freshness": "fresh",
        "confidence": "development_degraded",
        "health": "CP3_D_NOT_PROVEN",
        "source_ids": ["ctower:CT-I1-007", "mission-control:i1.7"],
        "derivation_reasons": [
            "criterion_missing:cp3_d",
            "effective_blocker:cp3_d",
            "underlying_maturity:verified",
        ],
    }
    payload: dict[str, object] = {
        "schema": "ctower.project-delivery/v1",
        "company_key": "ctower",
        "project_key": "ctower",
        "rows": [row],
    }

    validator.validate(payload)
    forbidden = {
        **payload,
        "rows": [{**row, "completion_percentage": 83}],
    }
    with pytest.raises(ValidationError):
        validator.validate(forbidden)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "blocked"})


def test_zero_declared_criteria_and_unknown_headline_are_not_contract_states() -> None:
    validator = _validator()
    row = {
        "checkpoint_key": "I1.7",
        "checkpoint_label": "Development dogfood cutover",
        "headline_state": "STATE_UNKNOWN",
        "underlying_maturity": "verified",
        "outcome": "reviewable cutover",
        "accountable_owner": "operator",
        "criteria": {"proven": 0, "declared": 0},
        "source_watermark": 0,
        "projection_watermark": 0,
        "freshness": "STATE_UNKNOWN",
        "confidence": "STATE_UNKNOWN",
        "health": "STATE_UNKNOWN",
        "source_ids": [],
        "derivation_reasons": ["source_incomplete"],
    }
    with pytest.raises(ValidationError):
        validator.validate(
            {
                "schema": "ctower.project-delivery/v1",
                "company_key": "ctower",
                "project_key": "ctower",
                "rows": [row],
            }
        )


def _validator() -> Draft202012Validator:
    path = ROOT / "contracts/domain/project-delivery/project-delivery.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
