"""Strict payloads for external-estate import facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "CompanyRecordAppendedPayload",
    "EstateImportChangedPayload",
]

_MAX_SOURCE_REF = 512
_MAX_NATURAL_KEY = 256
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEAT = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
_TIERS = frozenset(
    {"inbox_history", "agreed_decisions", "knowledge_documents", "company_records"}
)


@dataclass(frozen=True, slots=True)
class EstateImportChangedPayload:
    """One estate-import fact; it never mints a principal, seat, or grant."""

    tier: str
    manifest_digest: str
    operation: str
    source_ref: str

    def __post_init__(self) -> None:
        if self.tier not in _TIERS:
            raise ValueError("estate import tier is outside the authored contract")
        if self.operation not in {"parity_reported", "batch_applied", "tier_closed"}:
            raise ValueError("estate import operation is outside the authored contract")
        if _SHA256.fullmatch(self.manifest_digest) is None:
            raise ValueError("estate import manifest digest is outside the contract")
        if not self.source_ref or len(self.source_ref) > _MAX_SOURCE_REF:
            raise ValueError("estate import source reference is outside the contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "operation": self.operation,
            "source_ref": self.source_ref,
            "tier": self.tier,
        }


@dataclass(frozen=True, slots=True)
class CompanyRecordAppendedPayload:
    """One append-only company accountability row under tenant scope."""

    record_id: UUID
    record_type: str
    natural_key: str
    occurred_on: str
    seat: str
    payload_digest: str
    source_ref: str
    imported_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, UUID):
            raise TypeError("company record identity must be a UUID")
        if self.record_type != "escape":
            raise ValueError("company record type is outside the authored contract")
        if not self.natural_key or len(self.natural_key) > _MAX_NATURAL_KEY:
            raise ValueError("company record natural key is outside the contract")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.occurred_on):
            raise ValueError("company record occurred_on must be an ISO date")
        if _SEAT.fullmatch(self.seat) is None:
            raise ValueError("company record seat is outside the authored contract")
        if _SHA256.fullmatch(self.payload_digest) is None:
            raise ValueError("company record payload digest is outside the contract")
        if not self.source_ref or len(self.source_ref) > _MAX_SOURCE_REF:
            raise ValueError("company record source reference is outside the contract")
        if not isinstance(self.imported_at, datetime) or self.imported_at.tzinfo is None:
            raise ValueError("company record imported_at must be timezone-aware")

    def to_mapping(self) -> dict[str, object]:
        return {
            "imported_at": self.imported_at.isoformat(),
            "natural_key": self.natural_key,
            "occurred_on": self.occurred_on,
            "payload_digest": self.payload_digest,
            "record_id": str(self.record_id),
            "record_type": self.record_type,
            "seat": self.seat,
            "source_ref": self.source_ref,
        }
