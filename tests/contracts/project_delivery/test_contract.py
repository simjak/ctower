"""Project Delivery is generic, proof-aware, freshness-honest, and rebuildable."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from ._fixture import project_delivery_row, project_delivery_view

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "contracts/domain/project-delivery/project-delivery.schema.json"
VECTOR_PATH = ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json"
CHECKPOINT_SCHEMA_PATH = ROOT / "contracts/components/checkpoint.schema.json"
OPENAPI_PATH = ROOT / "contracts/http/openapi.yaml"
CHECKPOINT_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
FRESHNESS_SECONDS = 3600


def test_cross_domain_row_reports_exact_qualifying_stage_slot_coverage() -> None:
    validator = _validator()
    payload = project_delivery_view()

    validator.validate(payload)
    row = cast(list[dict[str, object]], payload["rows"])[0]
    assert (
        row["qualifying_stage_slots_filled"],
        row["qualifying_stage_slots_required"],
    ) == (1, 3)
    assert row["qualifying_stage_unfilled_or_unknown_slot_keys"] == [
        "approval-receipt",
        "archive-proof",
    ]
    missing_keys = project_delivery_row()
    del missing_keys["qualifying_stage_unfilled_or_unknown_slot_keys"]
    with pytest.raises(ValidationError):
        validator.validate(project_delivery_view(missing_keys))
    with pytest.raises(ValidationError):
        validator.validate(
            project_delivery_view(
                {
                    **project_delivery_row(),
                    "qualifying_stage_unfilled_or_unknown_slot_keys": [
                        "approval-receipt",
                        "approval-receipt",
                    ],
                }
            )
        )


def test_projection_remains_read_only_and_freshness_honest() -> None:
    validator = _validator()
    payload = project_delivery_view()
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "blocked"})
    with pytest.raises(ValidationError):
        validator.validate(
            project_delivery_view(
                {
                    **project_delivery_row(),
                    "completion_percentage": 67,
                }
            )
        )
    with pytest.raises(ValidationError):
        validator.validate(
            project_delivery_view(
                {
                    **project_delivery_row(),
                    "freshness": "STATE_UNKNOWN",
                    "health": "CURRENT",
                }
            )
        )
    validator.validate(
        project_delivery_view(
            {
                **project_delivery_row(),
                "freshness": "STATE_UNKNOWN",
                "health": "STATE_UNKNOWN",
            }
        )
    )


def test_development_verdict_can_complete_only_its_configured_checkpoint() -> None:
    validator = _validator()
    limited = {
        **project_delivery_row(),
        "headline_state": "done",
        "criteria": {"proven": 3, "declared": 3},
        "qualifying_stage_slots_filled": 3,
        "qualifying_stage_slots_required": 3,
        "qualifying_stage_unfilled_or_unknown_slot_keys": [],
        "confidence": "development_degraded",
        "health": "CP3_D_NOT_PROVEN",
        "durability": "CP3_D_NOT_PROVEN",
        "recovery": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "data_class": "RECONSTRUCTIBLE_ONLY",
        "derivation_reasons": ["claim_scope:configured_checkpoint_only"],
    }
    validator.validate(project_delivery_view(limited))

    verdict_scope = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))["verdict_scope"]
    assert verdict_scope["may_complete_configured_checkpoint"] is True
    assert verdict_scope["may_claim_full_increment"] is False
    assert verdict_scope["may_activate_successor_increment"] is False


def test_project_delivery_contracts_forbid_checkpoint_literal_branches() -> None:
    documents = _checkpoint_contract_documents()
    checkpoint_schemas = [
        schema for document in documents for schema in _checkpoint_key_schemas(document)
    ]

    assert len(checkpoint_schemas) == len(documents)
    for schema in checkpoint_schemas:
        assert "const" not in schema, "checkpoint_key must not select a literal"
        assert "enum" not in schema, "checkpoint_key must not enumerate configured values"
        assert schema.get("pattern") == CHECKPOINT_KEY_PATTERN


def test_frozen_vectors_define_generic_fold_freshness_and_carry_forward() -> None:
    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    freshness = vectors["freshness"]
    carry_forward = vectors["carry_forward"]

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
    assert freshness["recompute_after_seconds"] == FRESHNESS_SECONDS
    assert freshness["request_time_mutation"] is False
    assert freshness["accepted_position"] is None
    assert freshness["durability_state"] == "durability_pending"
    assert carry_forward["ordinary_generated_api_cli_only"] is True
    assert carry_forward["bulk_import_authority"] is False


def test_delete_then_rebuild_at_one_watermark_has_identical_semantic_bytes() -> None:
    first = project_delivery_row()
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


def _checkpoint_contract_documents() -> list[dict[str, object]]:
    openapi = cast(
        dict[str, object],
        json.loads(OPENAPI_PATH.read_text(encoding="utf-8")),
    )
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, object], components["schemas"])
    return [
        cast(
            dict[str, object],
            json.loads(CHECKPOINT_SCHEMA_PATH.read_text(encoding="utf-8")),
        ),
        cast(
            dict[str, object],
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
        ),
        cast(dict[str, object], schemas["ProjectDeliveryRow"]),
    ]


def _checkpoint_key_schemas(node: object) -> Iterator[dict[str, object]]:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            checkpoint = properties.get("checkpoint_key")
            if isinstance(checkpoint, dict):
                yield cast(dict[str, object], checkpoint)
        for value in node.values():
            yield from _checkpoint_key_schemas(value)
    elif isinstance(node, list):
        for value in node:
            yield from _checkpoint_key_schemas(value)


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
