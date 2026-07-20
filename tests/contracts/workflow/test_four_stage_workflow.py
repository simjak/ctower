"""Authored four-stage Workflow graph contract evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
WORKFLOW = "ctower.trust-spine-four-stage"


def test_four_stage_fixture_is_a_valid_domain_neutral_graph() -> None:
    schema = _load("contracts/workflow/workflow.schema.json")
    fixture = _load(f"packs/workflows/{WORKFLOW}/v1.yaml")

    Draft202012Validator(schema).validate(fixture)

    assert fixture["key"] == WORKFLOW
    assert fixture["revision"] == 1
    assert [stage["activity_class"] for stage in fixture["stages"]] == [
        "work",
        "work",
        "verification",
        "work",
    ]
    assert [(edge["from"], edge["to"]) for edge in fixture["transitions"]] == [
        ("capture", "frame"),
        ("frame", "verify"),
        ("verify", "close"),
    ]


def test_workflow_contract_home_contains_only_graph_authority() -> None:
    authored = {path.name for path in (ROOT / "contracts/workflow").glob("*.schema.json")}

    assert authored == {"review-plan.schema.json", "workflow.schema.json"}


def _load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / path).read_text(encoding="utf-8")))
