"""Typed commands and committed results for the knowledge document aggregate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from ctower_kernel.record.events import EventOrigin

__all__ = [
    "KnowledgeAddCommand",
    "KnowledgeAddResult",
    "KnowledgeDocument",
    "KnowledgeDocumentListResult",
]

_SCOPES = frozenset({"org", "project"})
_MAX_TITLE_LENGTH = 1024
_MAX_BODY_LENGTH = 1_048_576
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SOURCE_REF = re.compile(r"^[a-z][a-z0-9._/-]{0,511}$")


def _require_tz(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError("knowledge timestamps must be datetimes")
    if value.tzinfo is None:
        raise ValueError("knowledge timestamps must be timezone-aware")


def _require_project_key(scope: str, project_key: str | None) -> None:
    if scope == "org":
        if project_key is not None:
            raise ValueError("knowledge org scope must not carry a project_key")
        return
    if project_key is None or _PROJECT_KEY.fullmatch(project_key) is None:
        raise ValueError("knowledge project scope requires a valid project_key")


def _require_content(*, body: str | None, source_ref: str | None, title: str | None) -> None:
    direct = body is not None or title is not None
    sourced = source_ref is not None
    if direct == sourced:
        raise ValueError("knowledge content requires exactly body+title or source_ref")
    if sourced:
        if not isinstance(source_ref, str) or _SOURCE_REF.fullmatch(source_ref) is None:
            raise ValueError("knowledge source_ref is outside the authored contract")
        return
    if not isinstance(title, str) or not 1 <= len(title) <= _MAX_TITLE_LENGTH:
        raise ValueError("knowledge title is outside the authored contract")
    if not isinstance(body, str) or not 1 <= len(body) <= _MAX_BODY_LENGTH:
        raise ValueError("knowledge body is outside the authored contract")


def _require_import_content(*, body: str | None, source_ref: str | None, title: str | None) -> None:
    if source_ref is None or _SOURCE_REF.fullmatch(source_ref) is None:
        raise ValueError("knowledge source_ref is outside the authored contract")
    if not isinstance(title, str) or not 1 <= len(title) <= _MAX_TITLE_LENGTH:
        raise ValueError("knowledge title is outside the authored contract")
    if not isinstance(body, str) or not 1 <= len(body) <= _MAX_BODY_LENGTH:
        raise ValueError("knowledge body is outside the authored contract")


@dataclass(frozen=True, slots=True)
class KnowledgeAddCommand:
    """Register one direct or static-source knowledge document as an immutable snapshot."""

    client_command_id: UUID
    scope: str
    body: str | None = None
    project_key: str | None = None
    source_ref: str | None = None
    title: str | None = None
    recorded_at: datetime | None = None
    document_id: UUID | None = None
    origin: EventOrigin = EventOrigin.API

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("knowledge command identity must be a UUID")
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")
        _require_project_key(self.scope, self.project_key)
        if self.origin in {EventOrigin.MIGRATION_IMPORTER, EventOrigin.ESTATE_IMPORT}:
            _require_import_content(body=self.body, source_ref=self.source_ref, title=self.title)
        else:
            _require_content(body=self.body, source_ref=self.source_ref, title=self.title)

    def request_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"scope": self.scope}
        if self.project_key is not None:
            payload["project_key"] = self.project_key
        if self.source_ref is not None and self.origin not in {
            EventOrigin.MIGRATION_IMPORTER,
            EventOrigin.ESTATE_IMPORT,
        }:
            payload["source_ref"] = self.source_ref
        else:
            payload["body"] = cast(str, self.body)
            payload["title"] = cast(str, self.title)
            if self.source_ref is not None:
                payload["source_ref"] = self.source_ref
        if self.recorded_at is not None:
            payload["recorded_at"] = self.recorded_at.isoformat()
        if self.document_id is not None:
            payload["document_id"] = str(self.document_id)
        if self.origin is not EventOrigin.API:
            payload["origin"] = self.origin.value
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgeAddResult:
    command_id: UUID
    document_id: UUID
    event_id: UUID
    registered_at: datetime
    scope: str
    title: str
    project_key: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        _require_tz(self.registered_at)
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")
        _require_project_key(self.scope, self.project_key)

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "document_id": str(self.document_id),
            "durability_state": "durability_pending",
            "event_ids": [str(self.event_id)],
            "project_key": self.project_key,
            "registered_at": self.registered_at.isoformat(),
            "scope": self.scope,
            "source_ref": self.source_ref,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """A registered knowledge snapshot read from the disposable projection."""

    document_id: UUID
    scope: str
    title: str
    body: str
    registered_at: datetime
    registered_by: UUID
    project_key: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        _require_tz(self.registered_at)
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")
        _require_project_key(self.scope, self.project_key)
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= _MAX_TITLE_LENGTH:
            raise ValueError("knowledge title is outside the authored contract")
        if not isinstance(self.body, str) or not 1 <= len(self.body) <= _MAX_BODY_LENGTH:
            raise ValueError("knowledge body is outside the authored contract")
        if self.source_ref is not None and _SOURCE_REF.fullmatch(self.source_ref) is None:
            raise ValueError("knowledge source_ref is outside the authored contract")

    def response_payload(self) -> dict[str, object]:
        return {
            "body": self.body,
            "document_id": str(self.document_id),
            "project_key": self.project_key,
            "registered_at": self.registered_at.isoformat(),
            "registered_by": str(self.registered_by),
            "scope": self.scope,
            "source_ref": self.source_ref,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentListResult:
    scope: str
    documents: tuple[KnowledgeDocument, ...]
    project_key: str | None = None

    def __post_init__(self) -> None:
        if self.scope not in _SCOPES:
            raise ValueError("knowledge scope must be org or project")
        _require_project_key(self.scope, self.project_key)

    def response_payload(self) -> dict[str, object]:
        return {
            "documents": [item.response_payload() for item in self.documents],
            "project_key": self.project_key,
            "scope": self.scope,
        }


def add_result_from_committed(payload: dict[str, object]) -> KnowledgeAddResult:
    """Rebuild an add result from a committed response body (replay path)."""

    event_ids = cast(list[object], payload["event_ids"])
    project_key = payload.get("project_key")
    source_ref = payload.get("source_ref")
    return KnowledgeAddResult(
        UUID(str(payload["command_id"])),
        UUID(str(payload["document_id"])),
        UUID(str(event_ids[0])),
        datetime.fromisoformat(str(payload["registered_at"])).astimezone(UTC),
        str(payload["scope"]),
        str(payload["title"]),
        str(project_key) if project_key is not None else None,
        str(source_ref) if source_ref is not None else None,
    )
