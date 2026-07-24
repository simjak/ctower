"""Strict contracts for encrypted backup, anchors, inventory, and restore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
_I1_SOURCE_COUNT = 3
_RESTORE_STEP_COUNT = 12
_ARTIFACT_RPO_LIMIT = 300
_RTO_LIMIT = 14_400


def test_cp3c_contracts_are_strict_draft_2020_12_schemas() -> None:
    paths = (
        "contracts/evidence/object-manifest.schema.json",
        "contracts/operations/backup-manifest.schema.json",
        "contracts/operations/anchor.schema.json",
        "contracts/operations/expected-source-inventory.schema.json",
        "contracts/operations/restore-report.schema.json",
    )

    for relative in paths:
        schema = _json(relative)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False


def test_inventory_requires_all_three_explicit_i1_sources_and_no_empty_success() -> None:
    inventory = _json("contracts/operations/expected-source-inventory.schema.json")
    sources = cast(dict[str, object], cast(dict[str, object], inventory["properties"])["sources"])
    inactive = cast(dict[str, object], cast(dict[str, object], inventory["$defs"])["inactive"])
    properties = cast(dict[str, object], inactive["properties"])

    assert sources["minItems"] == _I1_SOURCE_COUNT
    assert sources["maxItems"] == _I1_SOURCE_COUNT
    assert properties["activation"] == {"const": "not_exercised"}
    assert properties["cursor_declaration"] == {"const": "zero_source"}
    assert properties["source_count"] == {"const": 0}
    source_keys = cast(list[str], cast(dict[str, object], properties["source_key"])["enum"])
    assert set(source_keys) == {
        "ctower.root-supervisor.default",
        "ctower.effect.default",
        "ctower.provider.default",
    }


def test_restore_report_pins_order_rpo_rto_and_effect_denial() -> None:
    restore = _json("contracts/operations/restore-report.schema.json")
    properties = cast(dict[str, object], restore["properties"])
    steps = cast(dict[str, object], properties["steps"])

    assert steps["minItems"] == steps["maxItems"] == _RESTORE_STEP_COUNT
    assert properties["accepted_rpo_seconds"] == {"const": 0}
    assert (
        cast(dict[str, object], properties["artifact_rpo_seconds"])["maximum"]
        == _ARTIFACT_RPO_LIMIT
    )
    assert cast(dict[str, object], properties["rto_seconds"])["maximum"] == _RTO_LIMIT
    assert properties["effects_enabled"] == {"const": False}


def _json(relative: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((ROOT / relative).read_text(encoding="utf-8")))
