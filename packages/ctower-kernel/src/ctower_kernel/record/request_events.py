"""Strict canonical payload for one complete Request state transition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["RequestChangedPayload"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_MAX_CONTENT = 65536
_MAX_SOURCE_KIND = 64
_MAX_SOURCE_REF = 256
_OPERATIONS = frozenset(
    {
        "capture",
        "import",
        "triage",
        "priority",
        "owner",
        "ticket_relation",
        "blocker",
        "closure_evaluation",
    }
)


@dataclass(frozen=True, slots=True)
class RequestChangedPayload:
    """One event-sufficient Request snapshot after an accepted semantic mutation."""

    operation: str
    request_id: UUID
    request_number: int
    project_key: str
    version: int
    content: str
    content_digest: str
    source_kind: str
    source_ref: str
    submitted_by: UUID
    owner_id: UUID
    triage: str
    priority: str
    priority_default: bool
    required_ticket_ids: tuple[UUID, ...]
    optional_ticket_ids: tuple[UUID, ...]
    blockers: tuple[str, ...]
    closure_outcome: str

    def __post_init__(self) -> None:
        _validate_header(self)
        _validate_content(self)
        _validate_state(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "blockers": list(self.blockers),
            "closure_outcome": self.closure_outcome,
            "content": self.content,
            "content_digest": self.content_digest,
            "operation": self.operation,
            "optional_ticket_ids": [str(item) for item in self.optional_ticket_ids],
            "owner_id": str(self.owner_id),
            "priority": self.priority,
            "priority_default": self.priority_default,
            "project_key": self.project_key,
            "request_id": str(self.request_id),
            "request_number": self.request_number,
            "required_ticket_ids": [str(item) for item in self.required_ticket_ids],
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "submitted_by": str(self.submitted_by),
            "triage": self.triage,
            "version": self.version,
        }


def _validate_header(payload: RequestChangedPayload) -> None:
    if payload.operation not in _OPERATIONS:
        raise ValueError("Request operation is outside the authored contract")
    identities = (payload.request_id, payload.submitted_by, payload.owner_id)
    if not all(isinstance(item, UUID) for item in identities):
        raise TypeError("Request identities must be UUIDs")
    if payload.request_number < 1 or payload.version < 1:
        raise ValueError("Request number and version must be positive")
    if _PROJECT.fullmatch(payload.project_key) is None:
        raise ValueError("Request project is outside the authored contract")


def _validate_content(payload: RequestChangedPayload) -> None:
    if not 1 <= len(payload.content) <= _MAX_CONTENT:
        raise ValueError("Request content is outside the authored contract")
    if _DIGEST.fullmatch(payload.content_digest) is None:
        raise ValueError("Request content is outside the authored contract")
    if not 1 <= len(payload.source_kind) <= _MAX_SOURCE_KIND:
        raise ValueError("Request source is outside the authored contract")
    if not 1 <= len(payload.source_ref) <= _MAX_SOURCE_REF:
        raise ValueError("Request source is outside the authored contract")


def _validate_state(payload: RequestChangedPayload) -> None:
    if payload.triage not in {"UNTRIAGED", "ACCEPTED", "DUPLICATE", "REJECTED"}:
        raise ValueError("Request triage is outside the authored contract")
    if payload.priority not in {"P0", "P1", "P2"}:
        raise ValueError("Request priority is outside the authored contract")
    relations = (*payload.required_ticket_ids, *payload.optional_ticket_ids)
    if not all(isinstance(item, UUID) for item in relations):
        raise TypeError("Request ticket relations must contain UUIDs")
    if payload.closure_outcome not in {"open", "done"}:
        raise ValueError("Request closure outcome is outside the authored contract")


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if isinstance(payload, RequestChangedPayload) and payload.request_id != aggregate_id:
        raise ValueError("Request event aggregate and payload identity must match")
