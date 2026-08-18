"""RED proof for the CT-I1-035 routine work-item boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parents[3]


def test_routine_v4_is_a_pointer_only_work_item_contract_without_session_dispatch() -> None:
    schema = cast(
        dict[str, object],
        json.loads((ROOT / "contracts/runtime/routine-v4.schema.json").read_text(encoding="utf-8")),
    )

    assert schema["title"] == "RoutineWorkItemRevision"
    assert "routine_item" in cast(list[str], schema["required"])
    assert "beat_dispatch" not in cast(list[str], schema["required"])
    assert "target_session" not in json.dumps(schema)

    item = cast(dict[str, object], cast(dict[str, object], schema["properties"])["routine_item"])
    assert item["$ref"] == "#/$defs/routineItem"
    routine_item = cast(dict[str, object], cast(dict[str, object], schema["$defs"])["routineItem"])
    assert routine_item["additionalProperties"] is False
    assert set(cast(list[str], routine_item["required"])) == {
        "item_key",
        "knowledge_ref",
        "owner_seat",
        "escalation_seat",
    }

    validator = Draft202012Validator(schema)
    valid = _valid_revision()
    validator.validate(valid)
    with pytest.raises(ValidationError):
        validator.validate(
            {
                **valid,
                "routine_item": {
                    **cast(dict[str, object], valid["routine_item"]),
                    "instructions": "do the work",
                },
            }
        )


def test_routine_item_contracts_are_strict_and_name_receipt_suppression_and_alarm_facts() -> None:
    expected = {
        "routine-work-item.schema.json": {"RoutineWorkItem", "knowledge_ref", "gate_evidence"},
        "routine-work-item-receipt.schema.json": {"RoutineWorkItemReceipt", "artifact_ref"},
        "routine-work-item-suppression.schema.json": {
            "RoutineWorkItemSuppression",
            "blocking_item_id",
        },
        "routine-work-item-alarm.schema.json": {"RoutineWorkItemAlarm", "escalation_seat"},
    }
    for filename, needles in expected.items():
        path = ROOT / "contracts/runtime" / filename
        assert path.is_file(), filename
        text = path.read_text(encoding="utf-8")
        assert '"additionalProperties": false' in text
        for needle in needles:
            assert needle in text, f"{needle} missing from {filename}"


def _valid_revision() -> dict[str, object]:
    return {
        "schema_id": "ctower.routine/v4",
        "routine_ref": "mc-cron.report@1",
        "revision_digest": "sha256:" + "a" * 64,
        "schedule": {
            "kind": "minute_hour_set",
            "timezone": "UTC",
            "minutes": [0],
            "hours": None,
        },
        "dst_policy": "wall_clock_once",
        "concurrency": "always_enqueue_bounded",
        "catch_up": "skip_missed",
        "catch_up_cap": 1,
        "timeout_seconds": 600,
        "handler_kind": "routine_item",
        "component_digests": ["sha256:" + "b" * 64],
        "activity_gate": {"kind": "always"},
        "routine_item": {
            "item_key": "report",
            "knowledge_ref": "routine-report",
            "owner_seat": "ctower-commander",
            "escalation_seat": "ctower-commander",
        },
    }
