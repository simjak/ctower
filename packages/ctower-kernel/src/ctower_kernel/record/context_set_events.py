"""Strict Board-card context-set event payloads, kept separate from Record envelope mechanics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["ChangeReferenceRecordedPayload", "LabelAppliedPayload"]

_LABEL_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_MAX_REPOSITORY_LENGTH = 256
_MAX_CHANGE_IDENTITY_LENGTH = 128
_MAX_REFERENCE_LENGTH = 256


@dataclass(frozen=True, slots=True)
class ChangeReferenceRecordedPayload:
    """INV-66: a Change fact linked to a ticket, recorded exactly as given."""

    change_reference_id: UUID
    ticket_id: UUID
    repository: str
    change_identity: str
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.change_reference_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("change reference identities must be UUIDs")
        if not 1 <= len(self.repository) <= _MAX_REPOSITORY_LENGTH:
            raise ValueError("change reference repository is outside the authored contract")
        if not 1 <= len(self.change_identity) <= _MAX_CHANGE_IDENTITY_LENGTH:
            raise ValueError("change reference identity is outside the authored contract")
        if not 1 <= len(self.reference) <= _MAX_REFERENCE_LENGTH:
            raise ValueError("change reference is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "change_identity": self.change_identity,
            "change_reference_id": str(self.change_reference_id),
            "reference": self.reference,
            "repository": self.repository,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class LabelAppliedPayload:
    """D29(b): an applied-label fact, pinned to the vocabulary revision active
    when it was applied."""

    ticket_label_id: UUID
    ticket_id: UUID
    label_key: str
    catalog_key: str
    catalog_revision: int
    catalog_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.ticket_label_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("label application identities must be UUIDs")
        if _LABEL_KEY.fullmatch(self.label_key) is None:
            raise ValueError("label key is outside the authored event contract")
        if _LABEL_KEY.fullmatch(self.catalog_key) is None:
            raise ValueError("label vocabulary catalog key is outside the authored contract")
        if self.catalog_revision < 1:
            raise ValueError("label vocabulary revision must be positive")
        if _DIGEST.fullmatch(self.catalog_digest) is None:
            raise ValueError("label vocabulary digest must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "catalog_digest": self.catalog_digest,
            "catalog_key": self.catalog_key,
            "catalog_revision": self.catalog_revision,
            "label_key": self.label_key,
            "ticket_id": str(self.ticket_id),
            "ticket_label_id": str(self.ticket_label_id),
        }
