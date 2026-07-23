"""Authored contracts for the CP3-B control-loop boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

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


def test_routine_revision_and_dst_outcome_vectors_are_deterministic() -> None:
    vectors = _json("contracts/runtime/routine-vectors.json")
    occurrence_schema = _json("contracts/runtime/routine-occurrence.schema.json")
    validator = Draft202012Validator(occurrence_schema)
    revisions = cast(list[dict[str, object]], vectors["revision_vectors"])
    occurrences = cast(list[dict[str, object]], vectors["occurrence_vectors"])

    for vector in revisions:
        pack = _json(str(vector["path"]))
        declared = pack.pop("revision_digest")
        canonical = json.dumps(pack, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        assert canonical == vector["canonical_json"]
        assert declared == vector["revision_digest"]
        assert declared == f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"

    for vector in occurrences:
        validator.validate(vector["occurrence"])
    outcomes = {cast(dict[str, object], vector["occurrence"])["outcome"] for vector in occurrences}
    assert {"queued", "skipped", "refused"} <= outcomes


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
