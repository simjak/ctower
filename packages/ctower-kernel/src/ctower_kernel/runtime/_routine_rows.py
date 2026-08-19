"""Decode persisted Routine rows into typed runtime values."""

from __future__ import annotations

from datetime import time
from typing import cast
from uuid import UUID

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    DreamDispatchSpec,
    RoutineRevision,
    ScheduleKind,
    _gate_sql,
)
from ctower_kernel.runtime.items import RoutineItemSpec


def revision(row: dict[str, object]) -> RoutineRevision:
    local_time = row["local_time"]
    if local_time is not None and not isinstance(local_time, time):
        raise TypeError("stored Routine local time is invalid")
    dream_dispatch = None
    if row.get("scope_kind") is not None:
        dream_dispatch = DreamDispatchSpec(
            scope_kind=str(row["scope_kind"]),
            project_key=str(row["project_key"]) if row["project_key"] is not None else None,
            skill_path=str(row["skill_path"]),
            primary_model_ref=str(row["primary_model_ref"]),
            primary_reasoning_effort=str(row["primary_reasoning_effort"]),
            fallback_model_ref=str(row["fallback_model_ref"]),
            fallback_reasoning_effort=str(row["fallback_reasoning_effort"]),
            minimum_model_tier=str(row["minimum_model_tier"]),
            excluded_model_families=tuple(cast(list[str], row["excluded_model_families"])),
        )
    routine_item = None
    if row.get("item_key") is not None:
        routine_item = RoutineItemSpec(
            item_key=str(row["item_key"]),
            knowledge_ref=str(row["knowledge_ref"]),
            document_id=cast(UUID, row["document_id"]),
            owner_seat=str(row["owner_seat"]),
            escalation_seat=str(row["escalation_seat"]),
        )
    return RoutineRevision(
        routine_ref=str(row["routine_ref"]),
        revision_digest="sha256:" + bytes(cast(bytes, row["revision_digest"])).hex(),
        schedule_kind=ScheduleKind(str(row["schedule_kind"])),
        timezone=str(row["timezone"]),
        local_time=local_time,
        concurrency=ConcurrencyPolicy(str(row["concurrency"])),
        catch_up=CatchUpPolicy(str(row["catch_up"])),
        catch_up_cap=int(cast(int, row["catch_up_cap"])),
        handler_kind=str(row["handler_kind"]),
        timeout_seconds=int(cast(int, row["timeout_seconds"])),
        component_digests=tuple(
            "sha256:" + bytes(cast(bytes, item)).hex()
            for item in cast(list[object], row["component_digests"])
        ),
        dream_dispatch=dream_dispatch,
        minute_marks=tuple(cast(list[int] | None, row["schedule_minutes"]) or ()),
        hour_marks=(
            tuple(cast(list[int], row["schedule_hours"]))
            if row["schedule_hours"] is not None
            else None
        ),
        routine_item=routine_item,
        activity_gate=_gate_sql.activity_gate_from_row(row),
    )
