"""Authored contract for the gh#433 fleet-beat boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]

EXPECTED = {
    "health": ({14, 34, 54}, None),
    "director-drive": ({4, 34}, None),
    "bhloop": ({9, 24, 39, 54}, None),
    "sprint": ({23}, {2, 8, 14, 20}),
    "digest": ({12}, {7}),
}
EXPECTED_PROMPT_DIGESTS = {
    "bhloop": "sha256:df64756b3616875f0b764f5662fcc27e4c29a4e13f00cfb54d94fbef8e9b6f5c",
    "digest": "sha256:fcf425433a5d4d75274ba1c631e3f6acdf24997388510b5406014601fc6a9775",
    "health": "sha256:eeb374713e45be8d0f5b1fdad7438e06698ccce0444d86f4496f3395b849aa22",
    "director-drive": "sha256:f2fcdf0589b945a89a6d29e404f33b1221f4e55c3987c1cf550212f258e3fe1c",
    "sprint": "sha256:a0fd8e11dbd81634d66025298bc60868c3cc5967bd3fc9e821fd53cb444ec963",
}
EXPECTED_TIMEZONES = {
    "bhloop": "UTC",
    "digest": "Europe/Vilnius",
    "health": "UTC",
    "director-drive": "UTC",
    "sprint": "Europe/Vilnius",
}


def test_five_fleet_beat_packs_pin_exact_prompts_and_schedules() -> None:
    schema = _json(ROOT / "contracts/runtime/routine-v3.schema.json")
    validator = Draft202012Validator(schema)

    for beat_key, (minutes, hours) in EXPECTED.items():
        pack = _json(ROOT / f"packs/routines/ctower.beat.{beat_key}/v1.yaml")
        validator.validate(pack)
        authored = {key: value for key, value in pack.items() if key != "revision_digest"}
        canonical = json.dumps(
            authored, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        assert pack["revision_digest"] == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        assert pack["routine_ref"] == f"ctower.beat.{beat_key}@1"
        assert pack["schedule"] == {
            "kind": "minute_hour_set",
            "timezone": EXPECTED_TIMEZONES[beat_key],
            "minutes": sorted(minutes),
            "hours": sorted(hours) if hours is not None else None,
        }
        dispatch = cast(dict[str, object], pack["beat_dispatch"])
        prompt_bytes = cast(str, dispatch["prompt"]).encode()
        if beat_key == "director-drive":
            assert prompt_bytes.endswith(b"\n")
        else:
            assert not prompt_bytes.endswith(b"\n")
        assert dispatch == {
            "beat_key": beat_key,
            "prompt_source": f"state/beats/{beat_key}.txt",
            "prompt_sha256": f"sha256:{hashlib.sha256(prompt_bytes).hexdigest()}",
            "prompt": prompt_bytes.decode(),
            "target_session": "commander",
        }
        assert dispatch["prompt_sha256"] == EXPECTED_PROMPT_DIGESTS[beat_key]


def test_beat_effect_contract_is_strict_and_http_list_is_authored() -> None:
    effect = _json(ROOT / "contracts/runtime/beat-dispatch-effect.schema.json")
    assert effect["additionalProperties"] is False
    properties = cast(dict[str, dict[str, object]], effect["properties"])
    assert properties["target_session"]["enum"] == ["commander", "mc-commander-manibo"]
    document = _json(ROOT / "contracts/http/openapi.yaml")
    paths = cast(dict[str, object], document["paths"])
    assert "/v1/runtime/beat-dispatches" in paths
    assert "/v1/runtime/beat-routines" in paths


def test_beat_retire_http_contract_is_strict_and_closed() -> None:
    document = _json(ROOT / "contracts/http/openapi.yaml")
    paths = cast(dict[str, dict[str, object]], document["paths"])
    operation = cast(
        dict[str, object],
        paths["/v1/runtime/beat-routines/{routine_ref}/retire"]["post"],
    )
    assert {
        key: operation[key]
        for key in (
            "operationId",
            "x-ctower-cli",
            "x-ctower-mutation",
            "x-ctower-principal",
            "x-ctower-spool",
        )
    } == {
        "operationId": "retireBeatRoutine",
        "x-ctower-cli": "beat-dispatch retire",
        "x-ctower-mutation": True,
        "x-ctower-principal": "operator",
        "x-ctower-spool": "forbidden",
    }
    assert "requestBody" not in operation
    assert operation["parameters"] == [
        {
            "name": "routine_ref",
            "in": "path",
            "required": True,
            "schema": {
                "type": "string",
                "pattern": r"^(ctower\.beat|mc-cron)\.[a-z][a-z0-9._-]*@[1-9][0-9]*$",
            },
        },
        {"$ref": "#/components/parameters/IdempotencyKey"},
    ]
    responses = cast(dict[str, dict[str, object]], operation["responses"])
    assert set(responses) == {"200", "202", "401", "403", "404", "409", "422"}
    for status in ("200", "202"):
        content = cast(dict[str, object], responses[status]["content"])
        assert content == {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/BeatRoutineRetirementReceipt"}
            }
        }

    components = cast(dict[str, object], document["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    receipt = schemas["BeatRoutineRetirementReceipt"]
    assert receipt["additionalProperties"] is False
    assert receipt["required"] == [
        "command_id",
        "retirement_id",
        "event_id",
        "routine_ref",
        "revision_digest",
        "retired_at",
        "durability_state",
    ]
    problem = schemas["Problem"]
    problem_properties = cast(dict[str, dict[str, object]], problem["properties"])
    problem_codes = cast(list[str], problem_properties["code"]["enum"])
    assert {
        "beat-routine-already-retired",
        "beat-routine-not-found",
        "beat-routine-retire-forbidden",
    } <= set(problem_codes)


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
