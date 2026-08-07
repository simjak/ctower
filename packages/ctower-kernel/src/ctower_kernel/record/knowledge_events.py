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
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SOURCE_REF = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576


def _require_registered_at(value: datetime) -> None:
    """Timezone-aware datetime is mandatory for the authored date-time wire contract."""
    if not isinstance(value, datetime):
        raise TypeError("knowledge registered_at must be a datetime")
    if value.tzinfo is None:
        raise ValueError("knowledge registered_at must be timezone-aware")


def _require_project_key(scope: str, project_key: str | None) -> str | None:
    if scope == "org":
        if project_key is not None:
            raise ValueError("knowledge org scope must not carry a project_key")
        return None
    if project_key is None or _PROJECT_KEY.fullmatch(project_key) is None:
        raise ValueError("knowledge project scope requires a valid project_key")
    return project_key


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRegisteredPayload:
    """A knowledge document was registered as an append-only fact."""

    body: str
    document_id: UUID
    registered_by: UUID
    registered_at: datetime
    scope: str
    title: str
    project_key: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, UUID):
            raise TypeError("knowledge document_id must be a UUID")
        if not isinstance(self.registered_by, UUID):
            raise TypeError("knowledge registered_by must be a UUID")
        _require_registered_at(self.registered_at)
        if _SCOPE.fullmatch(self.scope) is None:
            raise ValueError("knowledge scope must be org or project")
        _require_project_key(self.scope, self.project_key)
        if self.source_ref is not None and _SOURCE_REF.fullmatch(self.source_ref) is None:
            raise ValueError("knowledge source_ref is outside the authored contract")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= _MAX_TITLE_LENGTH:
            raise ValueError("knowledge title is outside the authored contract")
        if not isinstance(self.body, str) or not 1 <= len(self.body) <= _MAX_BODY_LENGTH:
            raise ValueError("knowledge body is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "body": self.body,
            "document_id": str(self.document_id),
            "project_key": self.project_key,
            "registered_by": str(self.registered_by),
            "registered_at": self.registered_at.isoformat(),
            "scope": self.scope,
            "source_ref": self.source_ref,
            "title": self.title,
        }


type KnowledgeEventPayload = KnowledgeDocumentRegisteredPayload


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if (
        isinstance(payload, KnowledgeDocumentRegisteredPayload)
        and aggregate_id != payload.document_id
    ):
        raise ValueError("knowledge aggregate and document identity must match")
