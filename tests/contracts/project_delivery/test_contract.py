"""Project Delivery is strict, proof-aware, freshness-honest, and rebuildable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "contracts/domain/project-delivery/project-delivery.schema.json"
VECTOR_PATH = ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json"
DIGEST = "sha256:" + ("0" * 64)
CHECKPOINT_COUNT = 14
I1_7_CRITERION_COUNT = 6
FRESHNESS_SECONDS = 3600


def _row() -> dict[str, object]:
    return {
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
        "durability": "CP3_D_NOT_PROVEN",
        "recovery": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "data_class": "RECONSTRUCTIBLE_ONLY",
        "semantic_digest": DIGEST,
        "reconciled_at": "2026-07-25T12:00:00Z",
        "freshness_due_at": "2026-07-25T13:00:00Z",
        "rebuild_generation": 1,
        "source_ids": ["ctower:CT-I1-007", "mission-control:i1.7"],
        "derivation_reasons": [
            "criterion_missing:disaster-safe-authority",
            "effective_blocker:disaster-safe-authority",
            "underlying_maturity:verified",
        ],
    }


def _view(row: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema": "ctower.project-delivery/v1",
        "company_key": "ctower",
        "project_key": "ctower",
        "source_record_position": 27,
        "projection_record_position": 27,
        "reconciled_at": "2026-07-25T12:00:00Z",
        "freshness_due_at": "2026-07-25T13:00:00Z",
        "projection_semantic_digest": DIGEST,
        "rebuild_generation": 1,
        "rows": [row or _row()],
    }


def test_i1_7_row_exposes_degraded_proof_coverage_without_writable_status() -> None:
    validator = _validator()
    payload = _view()
    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "blocked"})
    with pytest.raises(ValidationError):
        validator.validate(
            {
                **payload,
                "rows": [{**_row(), "completion_percentage": 83}],
            }
        )
    with pytest.raises(ValidationError):
        validator.validate(
            {
                **payload,
                "rows": [{**_row(), "headline_state": "done"}],
            }
        )


def test_stale_unknown_and_zero_criteria_cannot_advertise_current_delivery() -> None:
    validator = _validator()
    with pytest.raises(ValidationError):
        validator.validate(
            _view(
                {
                    **_row(),
                    "criteria": {"proven": 0, "declared": 0},
                    "freshness": "STATE_UNKNOWN",
                    "health": "CURRENT",
                }
            )
        )
    validator.validate(
        _view(
            {
                **_row(),
                "freshness": "STATE_UNKNOWN",
                "health": "STATE_UNKNOWN",
            }
        )
    )


def test_frozen_vectors_define_headline_order_freshness_and_rebuild_semantics() -> None:
    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    development = vectors["development_truth"]
    freshness = vectors["freshness"]

    assert len(vectors["checkpoint_keys"]) == CHECKPOINT_COUNT
    assert len(set(vectors["checkpoint_keys"])) == CHECKPOINT_COUNT
    assert len(vectors["i1_7_criteria"]) == I1_7_CRITERION_COUNT
    assert vectors["headline_precedence"] == [
        "done",
        "blocked",
        "released",
        "verified",
        "merged",
        "ready_to_land",
        "in_progress",
        "planned",
    ]
    assert development["durability"] == "CP3_D_NOT_PROVEN"
    assert development["recovery"] == "EXTERNAL_FAILURE_DOMAIN_UNPROVEN"
    assert development["data_class"] == "RECONSTRUCTIBLE_ONLY"
    assert freshness["recompute_after_seconds"] == FRESHNESS_SECONDS
    assert freshness["request_time_mutation"] is False
    assert freshness["accepted_position"] is None
    assert freshness["durability_state"] == "durability_pending"


def test_delete_then_rebuild_at_one_watermark_has_identical_semantic_bytes() -> None:
    first = _row()
    rebuilt = {
        **first,
        "reconciled_at": "2026-07-25T12:30:00Z",
        "freshness_due_at": "2026-07-25T13:30:00Z",
        "rebuild_generation": 2,
    }
    transient = {"reconciled_at", "freshness_due_at", "rebuild_generation", "freshness"}

    def semantic(row: dict[str, object]) -> bytes:
        payload = {key: value for key, value in row.items() if key not in transient}
        return rfc8785.dumps(cast(Any, payload))

    assert semantic(first) == semantic(rebuilt)
    assert first["source_ids"] == rebuilt["source_ids"]
    assert first["derivation_reasons"] == rebuilt["derivation_reasons"]


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
