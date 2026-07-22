"""Fixed-pack Routine registration and deterministic scheduler loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import cast
from uuid import UUID

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    Routine,
    RoutineRevision,
    ScheduleKind,
    SchedulerScan,
)

__all__: tuple[str, ...] = ()

_PACK_PATHS = (
    "routines/ctower.i1.synthetic-four-stage/v1.yaml",
    "routines/ctower.i1.daily-backup/v1.yaml",
    "routines/ctower.i1.record-anchor/v1.yaml",
)
_TOP_LEVEL_KEYS = frozenset(
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
_SCHEDULE_KEYS = frozenset({"kind", "timezone", "local_time"})


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
    """Load only the three authored packs and reject every untyped field."""

    revisions = tuple(_load_revision(pack_root / relative) for relative in _PACK_PATHS)
    references = {revision.routine_ref for revision in revisions}
    expected = {
        "ctower.i1.synthetic-four-stage@1",
        "ctower.i1.daily-backup@1",
        "ctower.i1.record-anchor@1",
    }
    if references != expected:
        raise ValueError("Routine packs do not declare the exact I1 revision set")
    return revisions


def _load_revision(path: Path) -> RoutineRevision:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    pack = _mapping(raw, "Routine pack")
    if frozenset(pack) != _TOP_LEVEL_KEYS:
        raise ValueError(f"Routine pack has unknown or missing fields: {path}")
    schedule = _mapping(pack["schedule"], "Routine schedule")
    if frozenset(schedule) != _SCHEDULE_KEYS:
        raise ValueError(f"Routine schedule has unknown or missing fields: {path}")
    if pack["schema_id"] != "ctower.routine/v1" or pack["dst_policy"] != "wall_clock_once":
        raise ValueError(f"Routine pack declares an unsupported contract or DST policy: {path}")
    local_time = _local_time(schedule["local_time"])
    return RoutineRevision(
        routine_ref=_string(pack["routine_ref"], "routine_ref"),
        revision_digest=_string(pack["revision_digest"], "revision_digest"),
        schedule_kind=ScheduleKind(_string(schedule["kind"], "schedule.kind")),
        timezone=_string(schedule["timezone"], "schedule.timezone"),
        local_time=local_time,
        concurrency=ConcurrencyPolicy(_string(pack["concurrency"], "concurrency")),
        catch_up=CatchUpPolicy(_string(pack["catch_up"], "catch_up")),
        catch_up_cap=_integer(pack["catch_up_cap"], "catch_up_cap"),
        handler_kind=_string(pack["handler_kind"], "handler_kind"),
        timeout_seconds=_integer(pack["timeout_seconds"], "timeout_seconds"),
        component_digests=_strings(pack["component_digests"], "component_digests"),
    )


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
