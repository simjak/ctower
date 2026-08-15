"""Typed commands, receipts, and accepted reads for Ruling facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ctower_kernel.record.events import EventOrigin

__all__ = [
    "RulingAppend",
    "RulingAppendResult",
    "RulingList",
    "RulingRow",
    "append_result_from_committed",
]


@dataclass(frozen=True, slots=True)
class RulingAppend:
    client_command_id: UUID
    verbatim: str
    supersedes_ruling_id: UUID | None = None
    request_id: UUID | None = None
    source_ref: str | None = None
    recorded_at: datetime | None = None
    project_key: str | None = None
    ruling_id: UUID | None = None
    origin: EventOrigin = EventOrigin.API

    def request_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "request_id": None if self.request_id is None else str(self.request_id),
            "supersedes_ruling_id": (
                None if self.supersedes_ruling_id is None else str(self.supersedes_ruling_id)
            ),
            "verbatim": self.verbatim,
        }
        if self.source_ref is not None:
            payload["source_ref"] = self.source_ref
        if self.recorded_at is not None:
            payload["recorded_at"] = self.recorded_at.isoformat()
        if self.project_key is not None:
            payload["project_key"] = self.project_key
        if self.ruling_id is not None:
            payload["ruling_id"] = str(self.ruling_id)
        if self.origin is not EventOrigin.API:
            payload["origin"] = self.origin.value
        return payload


@dataclass(frozen=True, slots=True)
class RulingAppendResult:
    command_id: UUID
    ruling_id: UUID
    event_id: UUID
    project_key: str
    recorded_by: UUID
    seat_key: str
    recorded_at: datetime
    supersedes_ruling_id: UUID | None
    request_id: UUID | None

    def response_payload(self) -> dict[str, object]:
        return {
            "accepted_position": None,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(self.event_id)],
            "project_key": self.project_key,
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": str(self.recorded_by),
            "request_id": None if self.request_id is None else str(self.request_id),
            "ruling_id": str(self.ruling_id),
            "seat_key": self.seat_key,
            "supersedes_ruling_id": (
                None if self.supersedes_ruling_id is None else str(self.supersedes_ruling_id)
            ),
        }


@dataclass(frozen=True, slots=True)
class RulingRow:
    ruling_id: UUID
    project_key: str
    verbatim: str
    verbatim_sha256: str
    recorded_by: UUID
    seat_key: str
    recorded_at: datetime
    supersedes_ruling_id: UUID | None
    superseded_by_ruling_id: UUID | None
    freshness: int
    request_id: UUID | None
    request_reference: str | None

    def response_payload(self) -> dict[str, object]:
        return {
            "durability_state": "accepted",
            "freshness": self.freshness,
            "project_key": self.project_key,
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": str(self.recorded_by),
            "request_id": None if self.request_id is None else str(self.request_id),
            "request_reference": self.request_reference,
            "ruling_id": str(self.ruling_id),
            "seat_key": self.seat_key,
            "superseded_by_ruling_id": (
                None if self.superseded_by_ruling_id is None else str(self.superseded_by_ruling_id)
            ),
            "supersedes_ruling_id": (
                None if self.supersedes_ruling_id is None else str(self.supersedes_ruling_id)
            ),
            "verbatim": self.verbatim,
            "verbatim_sha256": self.verbatim_sha256,
        }


@dataclass(frozen=True, slots=True)
class RulingList:
    rows: tuple[RulingRow, ...]
    answered_projects: tuple[str, ...]
    requested_projects: tuple[str, ...]
    unanswered_projects: tuple[str, ...]
    watermark: int
    observed_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "answered_project_count": len(self.answered_projects),
            "answered_projects": list(self.answered_projects),
            "observed_at": self.observed_at.isoformat(),
            "requested_project_count": len(self.requested_projects),
            "requested_projects": list(self.requested_projects),
            "rows": [row.response_payload() for row in self.rows],
            "unanswered_projects": list(self.unanswered_projects),
            "watermark": self.watermark,
        }


def append_result_from_committed(payload: dict[str, object]) -> RulingAppendResult:
    event_ids = payload["event_ids"]
    if not isinstance(event_ids, list) or len(event_ids) != 1:
        raise ValueError("committed Ruling result has an invalid event identity")
    supersedes = payload["supersedes_ruling_id"]
    request_id = payload["request_id"]
    return RulingAppendResult(
        UUID(str(payload["command_id"])),
        UUID(str(payload["ruling_id"])),
        UUID(str(event_ids[0])),
        str(payload["project_key"]),
        UUID(str(payload["recorded_by"])),
        str(payload["seat_key"]),
        datetime.fromisoformat(str(payload["recorded_at"])),
        None if supersedes is None else UUID(str(supersedes)),
        None if request_id is None else UUID(str(request_id)),
    )
