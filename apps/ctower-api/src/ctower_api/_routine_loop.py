"""Fixed-pack Routine registration and deterministic scheduler loop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import cast
from uuid import UUID

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    DreamDispatchSpec,
    Routine,
    RoutineRevision,
    ScheduleKind,
    SchedulerScan,
)
from ctower_kernel.runtime.beats import BeatDispatchSpec
from ctower_kernel.runtime.gates import ActivityGate

__all__: tuple[str, ...] = ()

_PACK_PATHS = (
    "routines/ctower.i1.synthetic-four-stage/v1.yaml",
    "routines/ctower.i1.daily-backup/v1.yaml",
    "routines/ctower.i1.record-anchor/v1.yaml",
    "routines/ctower.dream.manibo/v1.yaml",
    "routines/ctower.dream.ctower/v1.yaml",
    "routines/ctower.dream.bh-loop/v1.yaml",
    "routines/ctower.dream.fleet/v1.yaml",
    "routines/ctower.beat.health/v1.yaml",
    "routines/ctower.beat.director-drive/v1.yaml",
    "routines/ctower.beat.bhloop/v1.yaml",
    "routines/ctower.beat.sprint/v1.yaml",
    "routines/ctower.beat.digest/v1.yaml",
    "routines/mc-cron.manibo-report/v1.yaml",
    "routines/mc-cron.structural-report/v1.yaml",
    "routines/mc-cron.manibo-merge-watch/v1.yaml",
    "routines/mc-cron.worktree-janitor-apply/v1.yaml",
    "routines/mc-cron.capacity-sentinel/v1.yaml",
)
_EXPECTED_ROUTINE_REFS = frozenset(
    {
        "ctower.i1.synthetic-four-stage@1",
        "ctower.i1.daily-backup@1",
        "ctower.i1.record-anchor@1",
        "ctower.dream.manibo@1",
        "ctower.dream.ctower@1",
        "ctower.dream.bh-loop@1",
        "ctower.dream.fleet@1",
        "ctower.beat.health@1",
        "ctower.beat.director-drive@1",
        "ctower.beat.bhloop@1",
        "ctower.beat.sprint@1",
        "ctower.beat.digest@1",
        "mc-cron.manibo-report@1",
        "mc-cron.structural-report@1",
        "mc-cron.manibo-merge-watch@1",
        "mc-cron.worktree-janitor-apply@1",
        "mc-cron.capacity-sentinel@1",
    }
)
_TOP_LEVEL_KEYS_V1 = frozenset(
    {
        "schema_id",
        "routine_ref",
        "revision_digest",
        "schedule",
        "dst_policy",
        "concurrency",
        "catch_up",
        "catch_up_cap",
        "timeout_seconds",
        "handler_kind",
        "component_digests",
    }
)
_TOP_LEVEL_KEYS_V2 = _TOP_LEVEL_KEYS_V1 | {"dream_dispatch"}
_TOP_LEVEL_KEYS_V3 = _TOP_LEVEL_KEYS_V1 | {"beat_dispatch"}
_TOP_LEVEL_KEYS_V4 = _TOP_LEVEL_KEYS_V3 | {"activity_gate"}
_SUPPORTED_SCHEMA_IDS = frozenset(
    {
        "ctower.routine/v1",
        "ctower.routine/v2",
        "ctower.routine/v3",
        "ctower.routine/v4",
    }
)
_SCHEDULE_KEYS = frozenset({"kind", "timezone", "local_time"})
_BEAT_SCHEDULE_KEYS = frozenset({"kind", "timezone", "minutes", "hours"})
_DREAM_KEYS = frozenset({"scope_kind", "project_key", "skill_path", "model_requirement"})
_MODEL_KEYS = frozenset({"primary", "fallback", "minimum_tier", "excluded_families"})
_MODEL_SELECTION_KEYS = frozenset({"model_ref", "reasoning_effort"})
_BEAT_KEYS = frozenset({"beat_key", "prompt_source", "prompt_sha256", "prompt", "target_session"})
_GATE_KEYS = frozenset({"kind", "source", "threshold", "project_key"})


@dataclass(frozen=True, slots=True)
class RoutineLoop:
    """Own registration and scanning for the exact I1 Routine revisions."""

    runtime: Routine
    revisions: tuple[RoutineRevision, ...]

    def tick(self, tenant_ids: tuple[UUID, ...]) -> tuple[SchedulerScan, ...]:
        scans: list[SchedulerScan] = []
        for tenant_id in tenant_ids:
            for revision in self.revisions:
                self.runtime.register(tenant_id, revision)
            scans.append(self.runtime.scan(tenant_id))
        return tuple(scans)


def load_routine_revisions(pack_root: Path) -> tuple[RoutineRevision, ...]:
    """Load only the twelve authored packs and reject every untyped field."""

    revisions = tuple(_load_revision(pack_root / relative) for relative in _PACK_PATHS)
    references = {revision.routine_ref for revision in revisions}
    if references != _EXPECTED_ROUTINE_REFS:
        unexpected = ", ".join(sorted(references - _EXPECTED_ROUTINE_REFS)) or "none"
        missing = ", ".join(sorted(_EXPECTED_ROUTINE_REFS - references)) or "none"
        raise ValueError(
            "Routine packs do not declare the exact authored revision set: "
            f"unexpected={unexpected}; missing={missing}"
        )
    return revisions


def _load_revision(path: Path) -> RoutineRevision:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    pack = _mapping(raw, "Routine pack")
    schema_id = _string(pack.get("schema_id"), "schema_id")
    expected_keys = {
        "ctower.routine/v1": _TOP_LEVEL_KEYS_V1,
        "ctower.routine/v2": _TOP_LEVEL_KEYS_V2,
        "ctower.routine/v3": _TOP_LEVEL_KEYS_V3,
        "ctower.routine/v4": _TOP_LEVEL_KEYS_V4,
    }.get(schema_id, _TOP_LEVEL_KEYS_V1)
    if frozenset(pack) != expected_keys:
        raise ValueError(f"Routine pack has unknown or missing fields: {path}")
    schedule = _mapping(pack["schedule"], "Routine schedule")
    schedule_keys = (
        _BEAT_SCHEDULE_KEYS
        if schema_id in {"ctower.routine/v3", "ctower.routine/v4"}
        else _SCHEDULE_KEYS
    )
    if frozenset(schedule) != schedule_keys:
        raise ValueError(f"Routine schedule has unknown or missing fields: {path}")
    if schema_id not in _SUPPORTED_SCHEMA_IDS or pack["dst_policy"] != "wall_clock_once":
        raise ValueError(f"Routine pack declares an unsupported contract or DST policy: {path}")
    declared_digest = _string(pack["revision_digest"], "revision_digest")
    authored = {key: value for key, value in pack.items() if key != "revision_digest"}
    computed_digest = "sha256:" + hashlib.sha256(_canonical_bytes(authored)).hexdigest()
    if declared_digest != computed_digest:
        raise ValueError(f"Routine revision digest does not match authored content: {path}")
    local_time = _local_time(schedule.get("local_time"))
    dream_dispatch = _dream_dispatch(pack.get("dream_dispatch"))
    beat_dispatch = _beat_dispatch(pack.get("beat_dispatch"))
    activity_gate = _activity_gate(pack.get("activity_gate"))
    if (schema_id == "ctower.routine/v2") != (dream_dispatch is not None):
        raise ValueError(f"Routine contract version and effect facts do not match: {path}")
    if (schema_id in {"ctower.routine/v3", "ctower.routine/v4"}) != (beat_dispatch is not None):
        raise ValueError(f"Routine contract version and beat facts do not match: {path}")
    if (schema_id == "ctower.routine/v4") != (activity_gate is not None):
        raise ValueError(f"Routine contract version and gate facts do not match: {path}")
    return RoutineRevision(
        routine_ref=_string(pack["routine_ref"], "routine_ref"),
        revision_digest=declared_digest,
        schedule_kind=ScheduleKind(_string(schedule["kind"], "schedule.kind")),
        timezone=_string(schedule["timezone"], "schedule.timezone"),
        local_time=local_time,
        concurrency=ConcurrencyPolicy(_string(pack["concurrency"], "concurrency")),
        catch_up=CatchUpPolicy(_string(pack["catch_up"], "catch_up")),
        catch_up_cap=_integer(pack["catch_up_cap"], "catch_up_cap"),
        handler_kind=_string(pack["handler_kind"], "handler_kind"),
        timeout_seconds=_integer(pack["timeout_seconds"], "timeout_seconds"),
        component_digests=_strings(pack["component_digests"], "component_digests"),
        dream_dispatch=dream_dispatch,
        minute_marks=_integers(schedule.get("minutes"), "schedule.minutes"),
        hour_marks=_optional_integers(schedule.get("hours"), "schedule.hours"),
        beat_dispatch=beat_dispatch,
        activity_gate=activity_gate,
    )


def _activity_gate(value: object) -> ActivityGate | None:
    if value is None:
        return None
    gate = _mapping(value, "activity_gate")
    if not frozenset(gate) <= _GATE_KEYS:
        raise ValueError("activity_gate has unknown fields")
    return ActivityGate(
        kind=_string(gate["kind"], "activity_gate.kind"),
        source=(
            _string(gate["source"], "activity_gate.source")
            if gate.get("source") is not None
            else None
        ),
        threshold=(
            _integer(gate["threshold"], "activity_gate.threshold")
            if gate.get("threshold") is not None
            else None
        ),
        project_key=(
            _string(gate["project_key"], "activity_gate.project_key")
            if gate.get("project_key") is not None
            else None
        ),
    )


def _beat_dispatch(value: object) -> BeatDispatchSpec | None:
    if value is None:
        return None
    effect = _mapping(value, "beat_dispatch")
    if frozenset(effect) != _BEAT_KEYS:
        raise ValueError("beat_dispatch has unknown or missing fields")
    return BeatDispatchSpec(
        beat_key=_string(effect["beat_key"], "beat_key"),
        prompt_source=_string(effect["prompt_source"], "prompt_source"),
        prompt_sha256=_string(effect["prompt_sha256"], "prompt_sha256"),
        prompt=_string(effect["prompt"], "prompt"),
        target_session=_string(effect["target_session"], "target_session"),
    )


def _dream_dispatch(value: object) -> DreamDispatchSpec | None:
    if value is None:
        return None
    effect = _mapping(value, "dream_dispatch")
    if frozenset(effect) != _DREAM_KEYS:
        raise ValueError("dream_dispatch has unknown or missing fields")
    requirement = _mapping(effect["model_requirement"], "model_requirement")
    if frozenset(requirement) != _MODEL_KEYS:
        raise ValueError("model_requirement has unknown or missing fields")
    primary = _selection(requirement["primary"], "primary")
    fallback = _selection(requirement["fallback"], "fallback")
    project_key = effect["project_key"]
    if project_key is not None:
        project_key = _string(project_key, "project_key")
    return DreamDispatchSpec(
        scope_kind=_string(effect["scope_kind"], "scope_kind"),
        project_key=project_key,
        skill_path=_string(effect["skill_path"], "skill_path"),
        primary_model_ref=primary[0],
        primary_reasoning_effort=primary[1],
        fallback_model_ref=fallback[0],
        fallback_reasoning_effort=fallback[1],
        minimum_model_tier=_string(requirement["minimum_tier"], "minimum_tier"),
        excluded_model_families=_strings(requirement["excluded_families"], "excluded_families"),
    )


def _selection(value: object, field: str) -> tuple[str, str]:
    selection = _mapping(value, field)
    if frozenset(selection) != _MODEL_SELECTION_KEYS:
        raise ValueError(f"{field} has unknown or missing fields")
    return (
        _string(selection["model_ref"], f"{field}.model_ref"),
        _string(selection["reasoning_effort"], f"{field}.reasoning_effort"),
    )


def _canonical_bytes(value: dict[str, object]) -> bytes:
    """Render the complete authored revision body as deterministic UTF-8 JSON."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return cast(dict[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _integer(value: object, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return tuple(cast(list[str], value))


def _integers(value: object, field: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise ValueError(f"{field} must be an array of integers")
    return tuple(cast(list[int], value))


def _optional_integers(value: object, field: str) -> tuple[int, ...] | None:
    if value is None:
        return None
    return _integers(value, field)


def _local_time(value: object) -> time | None:
    if value is None:
        return None
    try:
        parsed = time.fromisoformat(_string(value, "schedule.local_time"))
    except ValueError as error:
        raise ValueError("schedule.local_time must be an ISO local time") from error
    if parsed.microsecond or parsed.tzinfo is not None:
        raise ValueError("schedule.local_time must have whole seconds and no offset")
    return parsed
