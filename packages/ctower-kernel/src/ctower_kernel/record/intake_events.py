"""Canonical payload variants for durable inbound-thread events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["InboundEventPromotedPayload", "InboundEventRecordedPayload", "IntakeEventPayload"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9._-]{2,127}$")
_OUTCOMES = frozenset(
    {"discussion", "ticket_created", "ticket_linked", "quarantined", "request_created"}
)
_INTENTS = frozenset({"discussion", "create_ticket", "link_ticket", "create_request"})
_TAINTS = frozenset({"authenticated", "external_untrusted", "quarantine_required"})
_MAX_SOURCE_KIND_LENGTH = 64
_MAX_SOURCE_REF_LENGTH = 256


@dataclass(frozen=True, slots=True)
class InboundEventRecordedPayload:
    inbound_event_id: UUID
    source_kind: str
    source_ref: str
    project_key: str
    position: int
    intent: str
    taint: str
    outcome: str
    content_digest: str
    ticket_id: UUID | None

    def __post_init__(self) -> None:
        if not isinstance(self.inbound_event_id, UUID):
            raise TypeError("inbound event identity must be a UUID")
        _validate_common(self.project_key, self.source_kind, self.source_ref)
        if self.position < 1:
            raise ValueError("inbound event position must be positive")
        if self.intent not in _INTENTS or self.taint not in _TAINTS:
            raise ValueError("inbound event intent or taint is outside the contract")
        if self.outcome not in _OUTCOMES or _DIGEST.fullmatch(self.content_digest) is None:
            raise ValueError("inbound event outcome or content digest is outside the contract")
        _validate_ticket_outcome(self.outcome, self.ticket_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "content_digest": self.content_digest,
            "inbound_event_id": str(self.inbound_event_id),
            "intent": self.intent,
            "outcome": self.outcome,
            "position": self.position,
            "project_key": self.project_key,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "taint": self.taint,
            "ticket_id": str(self.ticket_id) if self.ticket_id else None,
        }


@dataclass(frozen=True, slots=True)
class InboundEventPromotedPayload:
    inbound_event_id: UUID
    source_kind: str
    source_ref: str
    project_key: str
    intent: str
    outcome: str
    ticket_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.inbound_event_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("promotion identities must be UUIDs")
        _validate_common(self.project_key, self.source_kind, self.source_ref)
        if self.intent not in {"create_ticket", "link_ticket"}:
            raise ValueError("promotion intent must be actionable")
        if self.outcome not in {"ticket_created", "ticket_linked"}:
            raise ValueError("promotion outcome must contain one ticket edge")

    def to_mapping(self) -> dict[str, object]:
        return {
            "inbound_event_id": str(self.inbound_event_id),
            "intent": self.intent,
            "outcome": self.outcome,
            "project_key": self.project_key,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "ticket_id": str(self.ticket_id),
        }


type IntakeEventPayload = InboundEventRecordedPayload | InboundEventPromotedPayload


def _validate_identity(payload: object, stream_id: str, aggregate_id: UUID) -> None:
    if isinstance(payload, InboundEventRecordedPayload | InboundEventPromotedPayload) and (
        stream_id != f"inbound-thread:{aggregate_id}"
    ):
        raise ValueError("intake event must use its inbound thread stream")


def _validate_common(project_key: str, source_kind: str, source_ref: str) -> None:
    if _PROJECT_KEY.fullmatch(project_key) is None:
        raise ValueError("inbound project key is outside the contract")
    if (
        not 1 <= len(source_kind) <= _MAX_SOURCE_KIND_LENGTH
        or not 1 <= len(source_ref) <= _MAX_SOURCE_REF_LENGTH
    ):
        raise ValueError("inbound source alias is outside the contract")


def _validate_ticket_outcome(outcome: str, ticket_id: UUID | None) -> None:
    actionable = outcome in {"ticket_created", "ticket_linked"}
    if actionable != (ticket_id is not None):
        raise ValueError("inbound ticket outcome and ticket identity must agree")
