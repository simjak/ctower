"""Authored contracts for the CP3-B control-loop boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]


def test_runtime_and_outbox_contracts_are_strict_and_fixed_operation_only() -> None:
    routine = _json("contracts/runtime/routine.schema.json")
    occurrence = _json("contracts/runtime/routine-occurrence.schema.json")
    job = _json("contracts/runtime/operation-job.schema.json")
    delivery = _json("contracts/domain/outbox-delivery.schema.json")

    assert routine["additionalProperties"] is False
    handler = cast(
        dict[str, object], cast(dict[str, object], routine["properties"])["handler_kind"]
    )
    assert handler["enum"] == ["synthetic_four_stage", "daily_backup", "record_anchor"]
    assert occurrence["additionalProperties"] is False
    assert job["additionalProperties"] is False
    assert delivery["additionalProperties"] is False
    disposition = cast(dict[str, object], cast(dict[str, object], delivery["$defs"])["disposition"])
    assert cast(dict[str, object], disposition["properties"])["action"] == {
        "type": "string",
        "enum": ["retry", "tombstone"],
    }


def test_three_i1_routine_packs_pin_exact_schedule_policies() -> None:
    packs = {
        item["routine_ref"]: item
        for item in (
            _json("packs/routines/ctower.i1.synthetic-four-stage/v1.yaml"),
            _json("packs/routines/ctower.i1.daily-backup/v1.yaml"),
            _json("packs/routines/ctower.i1.record-anchor/v1.yaml"),
        )
    }

    assert set(packs) == {
        "ctower.i1.synthetic-four-stage@1",
        "ctower.i1.daily-backup@1",
        "ctower.i1.record-anchor@1",
    }
    assert packs["ctower.i1.synthetic-four-stage@1"]["handler_kind"] == "synthetic_four_stage"
    assert packs["ctower.i1.synthetic-four-stage@1"]["concurrency"] == "coalesce_if_active"
    assert packs["ctower.i1.synthetic-four-stage@1"]["catch_up"] == "skip_missed"
    assert packs["ctower.i1.daily-backup@1"]["concurrency"] == "serialize_one_pending"
    assert packs["ctower.i1.daily-backup@1"]["catch_up"] == "enqueue_missed_with_cap"
    assert packs["ctower.i1.daily-backup@1"]["catch_up_cap"] == 1
    anchor_schedule = cast(dict[str, object], packs["ctower.i1.record-anchor@1"]["schedule"])
    assert anchor_schedule["kind"] == "hourly"
    assert packs["ctower.i1.record-anchor@1"]["concurrency"] == "serialize_one_pending"
    assert packs["ctower.i1.record-anchor@1"]["catch_up"] == "coalesce_latest"


def test_health_contract_names_each_independent_cp3b_contributor() -> None:
    health = _json("contracts/operations/health.schema.json")
    dimension = cast(dict[str, object], cast(dict[str, object], health["$defs"])["dimension"])
    contributor = cast(dict[str, object], cast(dict[str, object], health["$defs"])["contributor"])

    assert dimension["required"] == ["status", "contributors"]
    assert contributor["additionalProperties"] is False
    assert cast(dict[str, object], contributor["properties"])["key"] == {
        "type": "string",
        "enum": [
            "durability",
            "scheduler",
            "outbox",
            "projection",
            "backup",
            "anchor",
            "object",
            "synthetic",
        ],
    }


def _json(relative: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((ROOT / relative).read_text(encoding="utf-8")))
