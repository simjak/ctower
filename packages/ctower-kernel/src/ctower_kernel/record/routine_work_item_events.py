"""Strict Record payloads for Routine work-item facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from ctower_kernel.record._event_types import EventKind, EventOrigin

__all__ = [
    "RoutineWorkItemAlarmRaisedPayload",
    "RoutineWorkItemAppendedPayload",
    "RoutineWorkItemCompletedPayload",
    "RoutineWorkItemEventPayload",
    "RoutineWorkItemSuppressedPayload",
    "validate_routine_work_item_identity",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_SEAT = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_KNOWLEDGE = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_MAX_ARTIFACT_REF = 512
_MAX_GATE_DETAIL = 500
_ALARM_KINDS = frozenset(
    {"missed_window", "degraded_read", "escalation_unresolved", "recovered_receipted"}
)
_UNRESOLVED_REASONS = frozenset({"missing", "stale", "revoked", "foreign_scope"})


@dataclass(frozen=True, slots=True)
class RoutineWorkItemAppendedPayload:
    work_item_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    window_ends_at: datetime
    owner_seat: str
    escalation_seat: str
    knowledge_ref: str
    document_id: UUID
    gate_evidence: dict[str, object]

    def __post_init__(self) -> None:
        _validate_common(
            self.routine_ref,
            self.revision_digest,
            self.owner_seat,
            self.escalation_seat,
        )
        _validate_uuid(self.work_item_id, "work_item_id")
        _validate_time(self.scheduled_for, "scheduled_for")
        _validate_time(self.window_ends_at, "window_ends_at")
        if self.window_ends_at <= self.scheduled_for:
            raise ValueError("Routine work-item window must end after it starts")
        if _KNOWLEDGE.fullmatch(self.knowledge_ref) is None:
            raise ValueError("Routine work-item Knowledge reference is invalid")
        _validate_uuid(self.document_id, "document_id")
        _validate_gate_evidence(self.gate_evidence)

    def to_mapping(self) -> dict[str, object]:
        return {
            "escalation_seat": self.escalation_seat,
            "gate_evidence": _gate_mapping(self.gate_evidence),
            "knowledge_ref": self.knowledge_ref,
            "document_id": str(self.document_id),
            "owner_seat": self.owner_seat,
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
            "scheduled_for": self.scheduled_for.isoformat(),
            "window_ends_at": self.window_ends_at.isoformat(),
            "work_item_id": str(self.work_item_id),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItemSuppressedPayload:
    suppression_id: UUID
    routine_ref: str
    scheduled_for: datetime
    blocking_item_id: UUID

    def __post_init__(self) -> None:
        _validate_uuid(self.suppression_id, "suppression_id")
        _validate_uuid(self.blocking_item_id, "blocking_item_id")
        if _REFERENCE.fullmatch(self.routine_ref) is None:
            raise ValueError("Routine suppression reference is invalid")
        _validate_time(self.scheduled_for, "scheduled_for")

    def to_mapping(self) -> dict[str, object]:
        return {
            "blocking_item_id": str(self.blocking_item_id),
            "routine_ref": self.routine_ref,
            "scheduled_for": self.scheduled_for.isoformat(),
            "suppression_id": str(self.suppression_id),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItemCompletedPayload:
    work_item_id: UUID
    receipt_id: UUID
    owner_seat: str
    artifact_ref: str
    delivered_at: datetime

    def __post_init__(self) -> None:
        _validate_uuid(self.work_item_id, "work_item_id")
        _validate_uuid(self.receipt_id, "receipt_id")
        if _SEAT.fullmatch(self.owner_seat) is None:
            raise ValueError("Routine completion owner seat is invalid")
        if (
            not isinstance(self.artifact_ref, str)
            or not 1 <= len(self.artifact_ref) <= _MAX_ARTIFACT_REF
        ):
            raise ValueError("Routine completion artifact reference is invalid")
        _validate_time(self.delivered_at, "delivered_at")

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_ref": self.artifact_ref,
            "delivered_at": self.delivered_at.isoformat(),
            "owner_seat": self.owner_seat,
            "receipt_id": str(self.receipt_id),
            "work_item_id": str(self.work_item_id),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItemAlarmRaisedPayload:
    alarm_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    work_item_id: UUID | None
    escalation_seat: str
    kind: str
    recorded_at: datetime
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.alarm_id, "alarm_id")
        if self.work_item_id is not None:
            _validate_uuid(self.work_item_id, "work_item_id")
        if _REFERENCE.fullmatch(self.routine_ref) is None:
            raise ValueError("Routine alarm reference is invalid")
        if _DIGEST.fullmatch(self.revision_digest) is None:
            raise ValueError("Routine alarm revision is invalid")
        _validate_time(self.scheduled_for, "scheduled_for")
        if _SEAT.fullmatch(self.escalation_seat) is None:
            raise ValueError("Routine alarm escalation seat is invalid")
        if self.kind not in _ALARM_KINDS:
            raise ValueError("Routine alarm kind is outside the authored contract")
        _validate_unresolved_reason(self.kind, self.unresolved_reason)
        _validate_time(self.recorded_at, "recorded_at")

    def to_mapping(self) -> dict[str, object]:
        return {
            "alarm_id": str(self.alarm_id),
            "escalation_seat": self.escalation_seat,
            "kind": self.kind,
            "recorded_at": self.recorded_at.isoformat(),
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
            "scheduled_for": self.scheduled_for.isoformat(),
            "unresolved_reason": self.unresolved_reason,
            "work_item_id": str(self.work_item_id) if self.work_item_id is not None else None,
        }


RoutineWorkItemEventPayload = (
    RoutineWorkItemAppendedPayload
    | RoutineWorkItemSuppressedPayload
    | RoutineWorkItemCompletedPayload
    | RoutineWorkItemAlarmRaisedPayload
)


_ROUTINE_WORK_ITEM_EVENT_CATALOG = (
    (
        EventKind.ROUTINE_WORK_ITEM_APPENDED,
        RoutineWorkItemAppendedPayload,
        frozenset({EventOrigin.CONTROL_WORKER}),
    ),
    (
        EventKind.ROUTINE_WORK_ITEM_SUPPRESSED,
        RoutineWorkItemSuppressedPayload,
        frozenset({EventOrigin.CONTROL_WORKER}),
    ),
    (
        EventKind.ROUTINE_WORK_ITEM_COMPLETED,
        RoutineWorkItemCompletedPayload,
        frozenset({EventOrigin.API}),
    ),
    (
        EventKind.ROUTINE_WORK_ITEM_ALARM_RAISED,
        RoutineWorkItemAlarmRaisedPayload,
        frozenset({EventOrigin.CONTROL_WORKER}),
    ),
)


def validate_routine_work_item_identity(aggregate_id: UUID, payload: object) -> None:
    if isinstance(payload, RoutineWorkItemAppendedPayload) and aggregate_id != payload.work_item_id:
        raise ValueError("Routine work-item aggregate and item identity must match")
    if (
        isinstance(payload, RoutineWorkItemSuppressedPayload)
        and aggregate_id != payload.suppression_id
    ):
        raise ValueError("Routine suppression aggregate and identity must match")
    if (
        isinstance(payload, RoutineWorkItemCompletedPayload)
        and aggregate_id != payload.work_item_id
    ):
        raise ValueError("Routine completion aggregate and item identity must match")
    if isinstance(payload, RoutineWorkItemAlarmRaisedPayload) and aggregate_id != payload.alarm_id:
        raise ValueError("Routine alarm aggregate and identity must match")


def _validate_common(
    routine_ref: str, revision_digest: str, owner_seat: str, escalation_seat: str
) -> None:
    if _REFERENCE.fullmatch(routine_ref) is None:
        raise ValueError("Routine work-item reference is invalid")
    if _DIGEST.fullmatch(revision_digest) is None:
        raise ValueError("Routine work-item revision is invalid")
    if _SEAT.fullmatch(owner_seat) is None or _SEAT.fullmatch(escalation_seat) is None:
        raise ValueError("Routine work-item seat is invalid")


def _validate_unresolved_reason(kind: str, reason: str | None) -> None:
    if (kind == "escalation_unresolved") != (reason is not None):
        raise ValueError("only an unresolved escalation alarm carries a reason")
    if reason is not None and reason not in _UNRESOLVED_REASONS:
        raise ValueError("Routine alarm unresolved reason is outside the authored contract")


def _validate_uuid(value: object, label: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{label} must be a UUID")


def _validate_time(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")


def _validate_gate_evidence(value: object) -> None:
    evidence = _gate_evidence_mapping(value)
    _validate_gate_kind(evidence["kind"])
    if evidence["result"] != "fired":
        raise ValueError("Routine work-item evidence must describe a fired gate")
    _validate_gate_watermark(evidence)
    _validate_gate_count(evidence["observed_count"])
    _validate_gate_detail(evidence["detail"])


def _gate_evidence_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("Routine gate evidence must be an object")
    expected = {
        "kind",
        "result",
        "watermark_kind",
        "watermark_position",
        "observed_count",
        "detail",
    }
    if set(value) != expected:
        raise ValueError("Routine gate evidence has unknown or missing fields")
    return cast(dict[str, object], value)


def _validate_gate_kind(value: object) -> None:
    if value not in {"always", "new_movement_since_watermark", "open_tickets_above"}:
        raise ValueError("Routine gate evidence kind is outside the closed set")


def _validate_gate_watermark(value: dict[str, object]) -> None:
    if value["watermark_kind"] not in {
        "none",
        "events.server_time",
        "tickets.server_time",
        "tickets.nonterminal",
    }:
        raise ValueError("Routine gate evidence watermark is invalid")
    position = value["watermark_position"]
    if isinstance(position, str):
        try:
            position = datetime.fromisoformat(position)
        except ValueError as error:
            raise ValueError("watermark_position must be an ISO timestamp") from error
    if position is not None:
        _validate_time(position, "watermark_position")


def _validate_gate_count(value: object) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("Routine gate evidence observed count is invalid")


def _validate_gate_detail(value: object) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_GATE_DETAIL:
        raise ValueError("Routine gate evidence detail is invalid")


def _gate_mapping(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    position = result.get("watermark_position")
    if isinstance(position, datetime):
        result["watermark_position"] = position.isoformat()
    return result
