"""Strict payloads for knowledge base document facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "KnowledgeDocumentRegisteredPayload",
    "KnowledgeEventPayload",
]

_SCOPE = re.compile(r"^(org|project)$")
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRegisteredPayload:
    """A knowledge document was registered as an append-only fact."""

    body: str
    document_id: UUID
    registered_by: UUID
    registered_at: datetime
    scope: str
    title: str

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, UUID):
            raise TypeError("knowledge document_id must be a UUID")
        if not isinstance(self.registered_by, UUID):
            raise TypeError("knowledge registered_by must be a UUID")
        if _SCOPE.fullmatch(self.scope) is None:
            raise ValueError("knowledge scope must be org or project")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= _MAX_TITLE_LENGTH:
            raise ValueError("knowledge title is outside the authored contract")
        if not isinstance(self.body, str) or not 1 <= len(self.body) <= _MAX_BODY_LENGTH:
            raise ValueError("knowledge body is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "body": self.body,
            "document_id": str(self.document_id),
            "registered_by": str(self.registered_by),
            "registered_at": self.registered_at.isoformat(),
            "scope": self.scope,
            "title": self.title,
        }


type KnowledgeEventPayload = KnowledgeDocumentRegisteredPayload


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if (
        isinstance(payload, KnowledgeDocumentRegisteredPayload)
        and aggregate_id != payload.document_id
    ):
        raise ValueError("knowledge aggregate and document identity must match")
