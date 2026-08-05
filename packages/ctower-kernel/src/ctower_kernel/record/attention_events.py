"""Strict Attention finding event payloads, kept separate from Record envelope mechanics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["AttentionFindingAppendedPayload", "AttentionFindingDispositionRecordedPayload"]

_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_REASON_CODE = re.compile(r"^[a-z][a-z0-9._-]*$")
_DEDUPE_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_MAX_TEXT = 500


@dataclass(frozen=True, slots=True)
class AttentionFindingAppendedPayload:
    """INV-67: one typed appended statement that work needs a human."""

    finding_id: UUID
    subject_ticket_id: UUID
    kind_key: str
    catalog_key: str
    catalog_revision: int
    catalog_digest: str
    reason_code: str
    effective_owner: str
    recommendation: str
    alternatives: tuple[str, ...]
    consequence: str
    deadline: datetime | None
    dedupe_key: str
    source_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate_identity_and_catalog()
        self._validate_content()

    def _validate_identity_and_catalog(self) -> None:
        if not isinstance(self.finding_id, UUID) or not isinstance(self.subject_ticket_id, UUID):
            raise TypeError("attention finding identities must be UUIDs")
        if _KEY.fullmatch(self.kind_key) is None:
            raise ValueError("attention finding kind is outside the authored contract")
        if _KEY.fullmatch(self.catalog_key) is None:
            raise ValueError("attention-kind catalog key is outside the authored contract")
        if self.catalog_revision < 1:
            raise ValueError("attention-kind catalog revision must be positive")
        if _DIGEST.fullmatch(self.catalog_digest) is None:
            raise ValueError("attention-kind catalog digest must be content addressed")

    def _validate_content(self) -> None:
        if _REASON_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("attention finding reason code is outside the authored contract")
        if self.effective_owner not in {"operator", "commander"}:
            raise ValueError("attention finding owner is outside the authored contract")
        if not 1 <= len(self.recommendation) <= _MAX_TEXT:
            raise ValueError("attention finding recommendation is outside the authored contract")
        if not 1 <= len(self.consequence) <= _MAX_TEXT:
            raise ValueError("attention finding consequence is outside the authored contract")
        if _DEDUPE_KEY.fullmatch(self.dedupe_key) is None:
            raise ValueError("attention finding dedupe key is outside the authored contract")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("attention finding deadline must be timezone-aware")

    def to_mapping(self) -> dict[str, object]:
        return {
            "alternatives": list(self.alternatives),
            "catalog_digest": self.catalog_digest,
            "catalog_key": self.catalog_key,
            "catalog_revision": self.catalog_revision,
            "consequence": self.consequence,
            "deadline": self.deadline.isoformat() if self.deadline is not None else None,
            "dedupe_key": self.dedupe_key,
            "effective_owner": self.effective_owner,
            "finding_id": str(self.finding_id),
            "kind_key": self.kind_key,
            "reason_code": self.reason_code,
            "recommendation": self.recommendation,
            "source_facts": list(self.source_facts),
            "subject_ticket_id": str(self.subject_ticket_id),
        }


@dataclass(frozen=True, slots=True)
class AttentionFindingDispositionRecordedPayload:
    """AC-ATT-02: resolution/snooze/expiry/supersession/cancellation is data."""

    disposition_id: UUID
    finding_id: UUID
    outcome: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition_id, UUID) or not isinstance(self.finding_id, UUID):
            raise TypeError("attention finding disposition identities must be UUIDs")
        if self.outcome not in {"resolved", "snoozed", "expired", "superseded", "cancelled"}:
            raise ValueError("attention finding disposition is outside the authored contract")
        if not 1 <= len(self.reason) <= _MAX_TEXT:
            raise ValueError(
                "attention finding disposition reason is outside the authored contract"
            )

    def to_mapping(self) -> dict[str, object]:
        return {
            "disposition_id": str(self.disposition_id),
            "finding_id": str(self.finding_id),
            "outcome": self.outcome,
            "reason": self.reason,
        }
