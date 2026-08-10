"""Strict canonical payload for one append-only Ruling fact."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["RulingRecordedPayload"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SEAT = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_MAX_VERBATIM_BYTES = 65536


@dataclass(frozen=True, slots=True)
class RulingRecordedPayload:
    """The exact words and seat attribution of one dated agreement."""

    ruling_id: UUID
    project_key: str
    verbatim: str
    verbatim_digest: str
    recorded_by: UUID
    seat_key: str
    recorded_at: datetime
    supersedes_ruling_id: UUID | None
    request_id: UUID | None
    decision_blocker_fact_id: UUID | None

    def __post_init__(self) -> None:
        _validate_identities(self)
        _validate_attribution(self)
        _validate_verbatim(self)
        _validate_timestamp(self.recorded_at)

    def to_mapping(self) -> dict[str, object]:
        return {
            "project_key": self.project_key,
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": str(self.recorded_by),
            "decision_blocker_fact_id": (
                None
                if self.decision_blocker_fact_id is None
                else str(self.decision_blocker_fact_id)
            ),
            "request_id": None if self.request_id is None else str(self.request_id),
            "ruling_id": str(self.ruling_id),
            "seat_key": self.seat_key,
            "supersedes_ruling_id": (
                None if self.supersedes_ruling_id is None else str(self.supersedes_ruling_id)
            ),
            "verbatim": self.verbatim,
            "verbatim_digest": self.verbatim_digest,
        }


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if isinstance(payload, RulingRecordedPayload) and payload.ruling_id != aggregate_id:
        raise ValueError("Ruling event aggregate and payload identity must match")


def _validate_identities(payload: RulingRecordedPayload) -> None:
    if not isinstance(payload.ruling_id, UUID) or not isinstance(payload.recorded_by, UUID):
        raise TypeError("Ruling identities must be UUIDs")
    predecessor = payload.supersedes_ruling_id
    if predecessor is not None and not isinstance(predecessor, UUID):
        raise TypeError("Ruling supersession identity must be a UUID or None")
    if payload.request_id is not None and not isinstance(payload.request_id, UUID):
        raise TypeError("Ruling Request identity must be a UUID or None")
    decision_fact = payload.decision_blocker_fact_id
    if decision_fact is not None and not isinstance(decision_fact, UUID):
        raise TypeError("Ruling decision occurrence identity must be a UUID or None")
    if (payload.request_id is None) != (decision_fact is None):
        raise ValueError("Ruling Request and decision occurrence must be named together")


def _validate_attribution(payload: RulingRecordedPayload) -> None:
    if _PROJECT.fullmatch(payload.project_key) is None:
        raise ValueError("Ruling project is outside the authored contract")
    if _SEAT.fullmatch(payload.seat_key) is None:
        raise ValueError("Ruling seat is outside the authored contract")


def _validate_verbatim(payload: RulingRecordedPayload) -> None:
    verbatim = payload.verbatim
    if not isinstance(verbatim, str):
        raise TypeError("Ruling verbatim must be text")
    if not 1 <= len(verbatim.encode("utf-8")) <= _MAX_VERBATIM_BYTES:
        raise ValueError("Ruling verbatim bytes are outside the authored contract")
    if "\x00" in verbatim or _DIGEST.fullmatch(payload.verbatim_digest) is None:
        raise ValueError("Ruling verbatim bytes are outside the authored contract")


def _validate_timestamp(recorded_at: datetime) -> None:
    if not isinstance(recorded_at, datetime) or recorded_at.tzinfo is None:
        raise ValueError("Ruling recorded_at must be timezone-aware")
