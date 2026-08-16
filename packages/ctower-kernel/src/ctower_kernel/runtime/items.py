"""Typed Runtime values for record-backed Routine work items."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

__all__ = [
    "CompleteRoutineWorkItemCommand",
    "RoutineAlarmKind",
    "RoutineGateEvidence",
    "RoutineItemSpec",
    "RoutineWorkItem",
    "RoutineWorkItemAlarm",
    "RoutineWorkItemReceipt",
    "RoutineWorkItemStatus",
    "RoutineWorkItemSuppression",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_KNOWLEDGE_REF = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_SEAT_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_MAX_ARTIFACT_REF = 512
_MAX_GATE_DETAIL = 500


class RoutineWorkItemStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class RoutineItemSpec:
    """Immutable Routine output metadata; policy content lives in Knowledge."""

    item_key: str
    knowledge_ref: str
    document_id: UUID
    owner_seat: str
    escalation_seat: str

    def __post_init__(self) -> None:
        if _STABLE_KEY.fullmatch(self.item_key) is None:
            raise ValueError("Routine item key must be stable")
        if _KNOWLEDGE_REF.fullmatch(self.knowledge_ref) is None:
            raise ValueError("Routine item must carry a Knowledge reference")
        if not isinstance(self.document_id, UUID):
            raise TypeError("Routine item must carry a Knowledge document UUID")
        if _SEAT_KEY.fullmatch(self.owner_seat) is None:
            raise ValueError("Routine item owner seat is outside the authored contract")
        if _SEAT_KEY.fullmatch(self.escalation_seat) is None:
            raise ValueError("Routine item escalation seat is outside the authored contract")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "escalation_seat": self.escalation_seat,
            "item_key": self.item_key,
            "knowledge_ref": self.knowledge_ref,
            "document_id": str(self.document_id),
            "owner_seat": self.owner_seat,
        }


@dataclass(frozen=True, slots=True)
class RoutineGateEvidence:
    """The typed gate result carried by a fired work item."""

    kind: str
    watermark_kind: str
    watermark_position: datetime | None
    observed_count: int
    detail: str
    result: str = "fired"

    def __post_init__(self) -> None:
        if self.kind not in {
            "always",
            "new_movement_since_watermark",
            "open_tickets_above",
        }:
            raise ValueError("Routine item gate kind is outside the closed set")
        if self.watermark_kind not in {
            "none",
            "events.server_time",
            "tickets.server_time",
            "tickets.nonterminal",
        }:
            raise ValueError("Routine item watermark kind is outside the authored contract")
        if self.result != "fired":
            raise ValueError("Routine work items carry only fired gate evidence")
        if type(self.observed_count) is not int or self.observed_count < 0:
            raise ValueError("Routine item observed count must be non-negative")
        if not isinstance(self.detail, str) or not 1 <= len(self.detail) <= _MAX_GATE_DETAIL:
            raise ValueError("Routine item gate detail is outside the authored contract")
        if self.watermark_position is not None and self.watermark_position.tzinfo is None:
            raise ValueError("Routine item watermark must be timezone-aware")

    def response_payload(self) -> dict[str, object]:
        return {
            "detail": self.detail,
            "kind": self.kind,
            "observed_count": self.observed_count,
            "result": self.result,
            "watermark_kind": self.watermark_kind,
            "watermark_position": (
                self.watermark_position.isoformat() if self.watermark_position is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItemReceipt:
    """Server-recorded proof that the owner delivered the artifact."""

    receipt_id: UUID
    work_item_id: UUID
    owner_seat: str
    artifact_ref: str
    delivered_at: datetime
    command_id: UUID | None = None
    event_id: UUID | None = None

    def __post_init__(self) -> None:
        _validate_receipt_identities(self)
        _validate_receipt_owner_and_artifact(self)
        _validate_receipt_time(self)
        _validate_receipt_commands(self)

    def response_payload(self) -> dict[str, object]:
        return {
            "artifact_ref": self.artifact_ref,
            "command_id": str(self.command_id) if self.command_id is not None else None,
            "delivered_at": self.delivered_at.isoformat(),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id) if self.event_id is not None else None,
            "owner_seat": self.owner_seat,
            "receipt_id": str(self.receipt_id),
            "work_item_id": str(self.work_item_id),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItem:
    """An Inbox-addressed Routine item with no embedded instruction text."""

    work_item_id: UUID
    tenant_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    window_ends_at: datetime
    owner_seat: str
    escalation_seat: str
    knowledge_ref: str
    document_id: UUID
    gate_evidence: RoutineGateEvidence
    created_at: datetime
    status: RoutineWorkItemStatus = RoutineWorkItemStatus.OPEN
    receipt: RoutineWorkItemReceipt | None = None

    def __post_init__(self) -> None:
        _validate_work_item_identities(self)
        _validate_work_item_reference(self)
        _validate_work_item_times(self)
        _validate_work_item_seats(self)
        _validate_work_item_shape(self)

    def response_payload(self) -> dict[str, object]:
        return {
            "escalation_seat": self.escalation_seat,
            "gate_evidence": self.gate_evidence.response_payload(),
            "knowledge_ref": self.knowledge_ref,
            "document_id": str(self.document_id),
            "owner_seat": self.owner_seat,
            "receipt": (
                {
                    "artifact_ref": self.receipt.artifact_ref,
                    "delivered_at": self.receipt.delivered_at.isoformat(),
                }
                if self.receipt is not None
                else None
            ),
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
            "schema_id": "ctower.routine-work-item/v1",
            "status": self.status.value,
            "tenant_id": str(self.tenant_id),
            "window": {
                "ends_at": self.window_ends_at.isoformat(),
                "scheduled_for": self.scheduled_for.isoformat(),
            },
            "work_item_id": str(self.work_item_id),
        }


@dataclass(frozen=True, slots=True)
class CompleteRoutineWorkItemCommand:
    client_command_id: UUID
    work_item_id: UUID
    artifact_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.work_item_id, UUID):
            raise TypeError("Routine work-item command identities must be UUIDs")
        if not isinstance(self.artifact_ref, str) or len(self.artifact_ref) > _MAX_ARTIFACT_REF:
            raise ValueError("Routine work-item completion artifact reference is invalid")

    def request_payload(self) -> dict[str, object]:
        return {
            "artifact_ref": self.artifact_ref,
            "work_item_id": str(self.work_item_id),
        }


@dataclass(frozen=True, slots=True)
class RoutineWorkItemSuppression:
    suppression_id: UUID
    routine_ref: str
    scheduled_for: datetime
    blocking_item_id: UUID
    recorded_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "blocking_item_id": str(self.blocking_item_id),
            "recorded_at": self.recorded_at.isoformat(),
            "routine_ref": self.routine_ref,
            "schema_id": "ctower.routine-work-item-suppression/v1",
            "suppression_id": str(self.suppression_id),
            "window": self.scheduled_for.isoformat(),
        }


def _validate_receipt_identities(receipt: RoutineWorkItemReceipt) -> None:
    if not isinstance(receipt.receipt_id, UUID) or not isinstance(receipt.work_item_id, UUID):
        raise TypeError("Routine work-item receipt identities must be UUIDs")


def _validate_receipt_owner_and_artifact(receipt: RoutineWorkItemReceipt) -> None:
    if _SEAT_KEY.fullmatch(receipt.owner_seat) is None:
        raise ValueError("Routine work-item receipt owner seat is invalid")
    if (
        not isinstance(receipt.artifact_ref, str)
        or not 1 <= len(receipt.artifact_ref) <= _MAX_ARTIFACT_REF
    ):
        raise ValueError("Routine work-item receipt requires a delivered artifact reference")


def _validate_receipt_time(receipt: RoutineWorkItemReceipt) -> None:
    if not isinstance(receipt.delivered_at, datetime) or receipt.delivered_at.tzinfo is None:
        raise ValueError("Routine work-item receipt time must be timezone-aware")


def _validate_receipt_commands(receipt: RoutineWorkItemReceipt) -> None:
    if receipt.command_id is not None and not isinstance(receipt.command_id, UUID):
        raise TypeError("Routine work-item receipt command_id must be a UUID")
    if receipt.event_id is not None and not isinstance(receipt.event_id, UUID):
        raise TypeError("Routine work-item receipt event_id must be a UUID")


def _validate_work_item_identities(item: RoutineWorkItem) -> None:
    if not isinstance(item.work_item_id, UUID) or not isinstance(item.tenant_id, UUID):
        raise TypeError("Routine work-item identities must be UUIDs")


def _validate_work_item_reference(item: RoutineWorkItem) -> None:
    if _REFERENCE.fullmatch(item.routine_ref) is None:
        raise ValueError("Routine work-item reference must be versioned")
    if _DIGEST.fullmatch(item.revision_digest) is None:
        raise ValueError("Routine work-item revision must be content addressed")


def _validate_work_item_times(item: RoutineWorkItem) -> None:
    for label, value in (
        ("scheduled_for", item.scheduled_for),
        ("window_ends_at", item.window_ends_at),
        ("created_at", item.created_at),
    ):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError(f"Routine work-item {label} must be timezone-aware")
    if item.window_ends_at <= item.scheduled_for:
        raise ValueError("Routine work-item window must end after it starts")


def _validate_work_item_seats(item: RoutineWorkItem) -> None:
    if (
        _SEAT_KEY.fullmatch(item.owner_seat) is None
        or _SEAT_KEY.fullmatch(item.escalation_seat) is None
    ):
        raise ValueError("Routine work-item seat is outside the authored contract")
    if _KNOWLEDGE_REF.fullmatch(item.knowledge_ref) is None:
        raise ValueError("Routine work-item Knowledge reference is invalid")
    if not isinstance(item.document_id, UUID):
        raise TypeError("Routine work-item Knowledge document must be a UUID")


def _validate_work_item_shape(item: RoutineWorkItem) -> None:
    if not isinstance(item.gate_evidence, RoutineGateEvidence):
        raise TypeError("Routine work-item gate evidence is required")
    if item.status is RoutineWorkItemStatus.OPEN and item.receipt is not None:
        raise ValueError("an open Routine work item cannot carry a receipt")
    if item.status is RoutineWorkItemStatus.CLOSED and item.receipt is None:
        raise ValueError("a closed Routine work item requires a receipt")


class RoutineAlarmKind(StrEnum):
    MISSED_WINDOW = "missed_window"
    DEGRADED_READ = "degraded_read"


@dataclass(frozen=True, slots=True)
class RoutineWorkItemAlarm:
    alarm_id: UUID
    routine_ref: str
    scheduled_for: datetime
    work_item_id: UUID | None
    escalation_seat: str
    kind: RoutineAlarmKind
    recorded_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "alarm_id": str(self.alarm_id),
            "escalation_seat": self.escalation_seat,
            "kind": self.kind.value,
            "recorded_at": self.recorded_at.isoformat(),
            "routine_ref": self.routine_ref,
            "schema_id": "ctower.routine-work-item-alarm/v1",
            "window": self.scheduled_for.isoformat(),
            "work_item_id": str(self.work_item_id) if self.work_item_id is not None else None,
        }
