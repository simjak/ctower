"""AC-RTN-01/04: closed typed gate set, strict registration, backlog enumeration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]


class GatedPackExpected(TypedDict):
    minutes: tuple[int, ...]
    hours: tuple[int, ...] | None
    gate: dict[str, object]
    item_key: str
    knowledge_ref: str
    document_id: str
    owner_seat: str
    escalation_seat: str


GATED_PACKS: dict[str, GatedPackExpected] = {
    "mc-cron.manibo-report@1": {
        "minutes": (0, 30),
        "hours": None,
        "gate": {"kind": "always"},
        "item_key": "manibo-report",
        "knowledge_ref": "mc-cron.manibo-report",
        "document_id": "a98100ac-1ac2-56f4-8754-e9550ebf67e7",
        "owner_seat": "manibo-commander",
        "escalation_seat": "ctower-commander",
    },
    "mc-cron.structural-report@1": {
        "minutes": (0,),
        "hours": None,
        "gate": {"kind": "always"},
        "item_key": "structural-report",
        "knowledge_ref": "mc-cron.structural-report",
        "document_id": "ff5bb90f-6eb6-5cf6-9469-3e80d34190fd",
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
    },
    "mc-cron.manibo-merge-watch@1": {
        "minutes": tuple(range(0, 60, 4)),
        "hours": None,
        "gate": {"kind": "new_movement_since_watermark", "source": "events"},
        "item_key": "manibo-merge-watch",
        "knowledge_ref": "mc-cron.manibo-merge-watch",
        "document_id": "5ef302e2-6eb4-59cd-a39a-be1c53aaa0ed",
        "owner_seat": "manibo-commander",
        "escalation_seat": "ctower-commander",
    },
    "mc-cron.worktree-janitor-apply@1": {
        "minutes": tuple(range(0, 60, 5)),
        "hours": None,
        "gate": {"kind": "always"},
        "item_key": "worktree-janitor-apply",
        "knowledge_ref": "mc-cron.worktree-janitor-apply",
        "document_id": "b82a0ce2-280e-5a05-af2d-acb051441e6e",
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
    },
    "mc-cron.capacity-sentinel@1": {
        "minutes": tuple(range(0, 60, 10)),
        "hours": None,
        "gate": {"kind": "open_tickets_above", "threshold": 0},
        "item_key": "capacity-sentinel",
        "knowledge_ref": "mc-cron.capacity-sentinel",
        "document_id": "1edc6d80-b92f-5cab-9a8b-df4728a96dfe",
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
    },
}

EXPECTED_UNMIGRATED_SCHEDULES = 17


def test_five_gated_packs_pin_exact_gate_schedule_and_digest() -> None:
    schema = _json(ROOT / "contracts/runtime/routine-v4.schema.json")
    validator = Draft202012Validator(schema)
    for routine_ref, expected in GATED_PACKS.items():
        pack = _json(ROOT / f"packs/routines/{routine_ref.split('@')[0]}/v1.yaml")
        validator.validate(pack)
        authored = {key: value for key, value in pack.items() if key != "revision_digest"}
        canonical = json.dumps(
            authored, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        assert pack["revision_digest"] == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        assert pack["routine_ref"] == routine_ref
        schedule = cast(dict[str, object], pack["schedule"])
        assert schedule["minutes"] == list(expected["minutes"])
        assert schedule["hours"] == expected["hours"]
        gate = cast(dict[str, object], pack["activity_gate"])
        assert gate == expected["gate"]
        assert pack["handler_kind"] == "routine_item"
        assert "beat_dispatch" not in pack
        item = cast(dict[str, object], pack["routine_item"])
        assert item == {
            "item_key": expected["item_key"],
            "knowledge_ref": expected["knowledge_ref"],
            "document_id": expected["document_id"],
            "owner_seat": expected["owner_seat"],
            "escalation_seat": expected["escalation_seat"],
        }
        document_path = (
            ROOT
            / "packages/ctower-kernel/src/ctower_kernel/knowledge/static/org"
            / f"{expected['knowledge_ref']}.md"
        )
        assert document_path.is_file()
        document = document_path.read_text(encoding="utf-8")
        assert "target_session" not in json.dumps(pack)
        assert document


def test_gate_set_is_closed_and_typed_with_no_expression_language() -> None:
    schema = _json(ROOT / "contracts/runtime/routine-v4.schema.json")
    gate = cast(dict[str, object], cast(dict[str, object], schema["$defs"])["activityGate"])
    properties = cast(dict[str, object], gate["properties"])
    assert set(properties) == {"kind", "source", "threshold", "project_key"}
    kinds = cast(dict[str, object], properties["kind"])
    assert set(cast(list[str], kinds["enum"])) == {
        "always",
        "new_movement_since_watermark",
        "open_tickets_above",
    }
    sources = cast(dict[str, object], properties["source"])
    assert set(cast(list[str], sources["enum"])) == {"events", "tickets"}
    text = json.dumps(schema)
    for forbidden in ("expression", "cel", "jsonata", "sql", "script"):
        assert forbidden not in text.lower(), f"gate contract leaks {forbidden}"


def test_gate_evaluation_contract_is_strict_and_names_watermarks() -> None:
    evaluation = _json(ROOT / "contracts/runtime/routine-gate-evaluation.schema.json")
    assert evaluation["additionalProperties"] is False
    properties = cast(dict[str, dict[str, object]], evaluation["properties"])
    assert set(properties) == {
        "evaluation_id",
        "routine_ref",
        "revision_digest",
        "scheduled_for",
        "gate_kind",
        "result",
        "watermark_kind",
        "watermark_position",
        "observed_count",
        "detail",
        "evaluated_at",
    }
    results = properties["result"]
    assert set(cast(list[str], results["enum"])) == {"fired", "skipped", "degraded"}
    watermark_kinds = properties["watermark_kind"]
    assert set(cast(list[str], watermark_kinds["enum"])) == {
        "none",
        "events.server_time",
        "tickets.server_time",
        "tickets.nonterminal",
    }


def test_unmigrated_schedules_are_enumerated_with_intended_gates() -> None:
    backlog = _json(ROOT / "contracts/runtime/routine-migration-backlog.json")
    assert backlog["schema"] == "ctower.routine-migration-backlog/v1"
    migrated = cast(list[str], backlog["migrated"])
    assert set(migrated) == set(GATED_PACKS)
    admitted_backlog = cast(list[dict[str, object]], backlog["admitted_backlog"])
    assert admitted_backlog == [
        {
            "item": "routine-catch-parity-report-emitter",
            "status": "admitted-shim-debt",
            "reason": (
                "Ctower records routine fire facts but cannot observe host crontab state; "
                "the parity-report emitter remains outside this candidate."
            ),
        }
    ]
    entries = cast(list[dict[str, object]], backlog["unmigrated"])
    assert len(entries) == EXPECTED_UNMIGRATED_SCHEDULES
    gates = {cast(dict[str, object], entry["activity_gate"])["kind"] for entry in entries}
    assert gates <= {"always", "new_movement_since_watermark", "open_tickets_above"}
    for entry in entries:
        assert entry["cron_tool"]
        assert entry["schedule"]
        assert entry["owner_seat"]
        cast(dict[str, object], entry["activity_gate"])


def _json(relative: str | Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(Path(relative).read_text(encoding="utf-8")))
