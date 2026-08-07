"""Typed commands and committed results for the knowledge base aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

__all__ = [
    "KnowledgeAddCommand",
    "KnowledgeAddResult",
    "KnowledgeDocument",
    "KnowledgeDocumentListResult",
]

_SCOPES = frozenset({"org", "project"})
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576


def _require_tz(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("knowledge timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class KnowledgeAddCommand:
    """Register one knowledge document (org or project scope) as an append-only fact."""

    body: str
    client_command_id: UUID
    scope: str
    title: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("knowledge command identity must be a UUID")
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= _MAX_TITLE_LENGTH:
            raise ValueError("knowledge title is outside the authored contract")
        if not isinstance(self.body, str) or not 1 <= len(self.body) <= _MAX_BODY_LENGTH:
            raise ValueError("knowledge body is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "body": self.body,
            "scope": self.scope,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAddResult:
    command_id: UUID
    document_id: UUID
    event_id: UUID
    registered_at: datetime
    scope: str
    title: str

    def __post_init__(self) -> None:
        _require_tz(self.registered_at)

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "document_id": str(self.document_id),
            "durability_state": "durability_pending",
            "event_ids": [str(self.event_id)],
            "registered_at": self.registered_at.isoformat(),
            "scope": self.scope,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One registered knowledge document as read back from the projection."""

    document_id: UUID
    scope: str
    title: str
    body: str
    registered_at: datetime
    registered_by: UUID

    def __post_init__(self) -> None:
        _require_tz(self.registered_at)
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")

    def response_payload(self) -> dict[str, object]:
        return {
            "body": self.body,
            "document_id": str(self.document_id),
            "registered_at": self.registered_at.isoformat(),
            "registered_by": str(self.registered_by),
            "scope": self.scope,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentListResult:
    scope: str
    documents: tuple[KnowledgeDocument, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "documents": [item.response_payload() for item in self.documents],
            "scope": self.scope,
        }


def add_result_from_committed(payload: dict[str, object]) -> KnowledgeAddResult:
    """Rebuild an add result from a committed response body (replay path)."""

    event_ids = cast(list[object], payload["event_ids"])
    return KnowledgeAddResult(
        UUID(str(payload["command_id"])),
        UUID(str(payload["document_id"])),
        UUID(str(event_ids[0])),
        datetime.fromisoformat(str(payload["registered_at"])).astimezone(UTC),
        str(payload["scope"]),
        str(payload["title"]),
    )
