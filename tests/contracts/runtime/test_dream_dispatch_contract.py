"""Authored contract for the gh#368 nightly dream-dispatch boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]

_PACKS = (
    "packs/routines/ctower.dream.manibo/v1.yaml",
    "packs/routines/ctower.dream.ctower/v1.yaml",
    "packs/routines/ctower.dream.bh-loop/v1.yaml",
    "packs/routines/ctower.dream.fleet/v1.yaml",
)


def test_four_nightly_dream_packs_carry_the_exact_effect_facts() -> None:
    schema = _json("contracts/runtime/routine-v2.schema.json")
    validator = Draft202012Validator(schema)
    packs = tuple(_json(path) for path in _PACKS)

    for pack in packs:
        validator.validate(pack)
        authored = {key: value for key, value in pack.items() if key != "revision_digest"}
        canonical = json.dumps(
            authored, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        assert pack["revision_digest"] == f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    assert {cast(str, pack["routine_ref"]) for pack in packs} == {
        "ctower.dream.manibo@1",
        "ctower.dream.ctower@1",
        "ctower.dream.bh-loop@1",
        "ctower.dream.fleet@1",
    }
    assert {cast(dict[str, object], pack["dream_dispatch"])["scope_kind"] for pack in packs} == {
        "project",
        "fleet",
    }
    assert {cast(dict[str, object], pack["dream_dispatch"])["project_key"] for pack in packs} == {
        "manibo",
        "ctower",
        "bh-loop",
        None,
    }
    assert all(
        cast(dict[str, object], pack["schedule"])
        == {"kind": "daily", "timezone": "UTC", "local_time": "02:00:00"}
        for pack in packs
    )
    for pack in packs:
        effect = cast(dict[str, object], pack["dream_dispatch"])
        requirement = cast(dict[str, object], effect["model_requirement"])
        assert effect["skill_path"] == "skills/dreamer/SKILL.md"
        assert requirement == {
            "primary": {"model_ref": "gpt-5.6-sol", "reasoning_effort": "max"},
            "fallback": {"model_ref": "qwen3.8-max", "reasoning_effort": "max"},
            "minimum_tier": "hard",
            "excluded_families": ["claude"],
        }


def test_dream_effect_and_http_contracts_are_strict_and_named() -> None:
    effect = _json("contracts/runtime/dream-dispatch-effect.schema.json")
    assert effect["additionalProperties"] is False
    document = _json("contracts/http/openapi.yaml")
    paths = cast(dict[str, object], document["paths"])
    assert "/v1/runtime/dream-dispatches" in paths
    assert "/v1/runtime/dream-dispatches/{effect_id}/consume" in paths
    schemas = cast(dict[str, object], cast(dict[str, object], document["components"])["schemas"])
    problem = cast(dict[str, object], schemas["Problem"])
    code = cast(dict[str, object], cast(dict[str, object], problem["properties"])["code"])
    expected = {
        "dream-dispatch-already-consumed",
        "dream-dispatch-family-excluded",
        "dream-dispatch-lane-unbound",
        "dream-dispatch-model-requirement-mismatch",
        "dream-dispatch-tier-refused",
        "dream-dispatch-unavailable",
    }
    assert expected <= set(cast(list[str], code["enum"]))


def test_operator_dream_lane_binding_surface_is_authored() -> None:
    document = _json("contracts/http/openapi.yaml")
    paths = cast(dict[str, object], document["paths"])
    operation = cast(
        dict[str, object],
        cast(dict[str, object], paths["/v1/runtime/dream-lane-bindings"])["post"],
    )

    assert operation["operationId"] == "bindDreamLane"
    assert operation["x-ctower-cli"] == "dream-lane bind"
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["x-ctower-mutation"] is True


def test_dream_lane_binding_refusals_are_named() -> None:
    document = _json("contracts/http/openapi.yaml")
    schemas = cast(dict[str, object], cast(dict[str, object], document["components"])["schemas"])
    problem = cast(dict[str, object], schemas["Problem"])
    code = cast(dict[str, object], cast(dict[str, object], problem["properties"])["code"])

    assert {
        "dream-lane-already-bound",
        "dream-lane-binding-operator-required",
    } <= set(cast(list[str], code["enum"]))


def _json(relative: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((ROOT / relative).read_text(encoding="utf-8")))
