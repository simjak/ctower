"""Execution-owned CP-1 policy contract evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
WORKFLOW_REF = "ctower.trust-spine-four-stage@1"


def test_execution_home_owns_and_validates_all_three_consumer_policies() -> None:
    pairs = (
        ("execution-policy", "execution/trust-spine-four-stage-v1.yaml"),
        ("gate-policy", "gates/trust-spine-four-stage-v1.yaml"),
        ("evidence-policy", "evidence/trust-spine-four-stage-v1.yaml"),
    )
    for schema_name, pack_path in pairs:
        schema = _load(f"contracts/execution/{schema_name}.schema.json")
        pack = _load(f"packs/policies/{pack_path}")
        Draft202012Validator(schema).validate(pack)
        assert schema["$id"] == (
            f"https://ctower.invalid/contracts/execution/{schema_name}.schema.json"
        )


def test_fixture_policy_references_and_deferred_capabilities_are_exact() -> None:
    execution = _load("packs/policies/execution/trust-spine-four-stage-v1.yaml")
    gate = _load("packs/policies/gates/trust-spine-four-stage-v1.yaml")
    evidence = _load("packs/policies/evidence/trust-spine-four-stage-v1.yaml")

    assert execution["workflow_ref"] == WORKFLOW_REF
    assert gate["workflow_ref"] == WORKFLOW_REF
    assert gate["evidence_policy_ref"] == "ctower.trust-spine-four-stage.evidence@1"
    capabilities = cast(dict[str, str], execution["capabilities"])
    assert capabilities == {
        "remote": "not_exercised",
        "images": "not_exercised",
        "effects": "not_exercised",
        "extensions": "not_exercised",
    }
    assert evidence["candidate_binding"] == "current_digest"
    assert evidence["corruption_policy"] == "reject"


def _load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / path).read_text(encoding="utf-8")))
