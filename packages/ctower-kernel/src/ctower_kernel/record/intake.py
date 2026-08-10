"""Typed inbound-thread commands and exact semantic results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

__all__ = [
    "InboundSource",
    "IntakeCommandResult",
    "IntakeIntent",
    "IntakeOutcome",
    "IntakePromotionCommand",
    "IntakeSubmitCommand",
    "IntakeTaint",
]


class IntakeIntent(StrEnum):
    """Explicit caller-selected intake semantics; no classifier is involved."""

    DISCUSSION = "discussion"
    CREATE_REQUEST = "create_request"
    CREATE_TICKET = "create_ticket"
    LINK_TICKET = "link_ticket"


class IntakeTaint(StrEnum):
    """Structural ingress taint supplied by the trusted adapter."""

    AUTHENTICATED = "authenticated"
    EXTERNAL_UNTRUSTED = "external_untrusted"
    QUARANTINE_REQUIRED = "quarantine_required"


class IntakeOutcome(StrEnum):
    """One durable semantic outcome for an inbound event."""

    DISCUSSION = "discussion"
    REQUEST_CREATED = "request_created"
    TICKET_CREATED = "ticket_created"
    TICKET_LINKED = "ticket_linked"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class InboundSource:
    """Stable source alias for exactly one immutable inbound event."""

    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class IntakeSubmitCommand:
    """Create or append one inbound event and apply its explicit initial intent."""

    client_command_id: UUID
    project_key: str
    source: InboundSource
    content: str
    intent: IntakeIntent = IntakeIntent.DISCUSSION
    taint: IntakeTaint = IntakeTaint.AUTHENTICATED
    thread_id: UUID | None = None
    expected_thread_version: int | None = None
    initial_custodian_id: UUID | None = None
    priority: str | None = None
    title: str | None = None
    target_ticket_id: UUID | None = None
    expected_ticket_version: int | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            "content": self.content,
            "expected_thread_version": self.expected_thread_version,
            "expected_ticket_version": self.expected_ticket_version,
            "initial_custodian_id": (
                str(self.initial_custodian_id) if self.initial_custodian_id else None
            ),
            "intent": self.intent.value,
            "priority": self.priority,
            "project_key": self.project_key,
            "source": asdict(self.source),
            "taint": self.taint.value,
            "target_ticket_id": str(self.target_ticket_id) if self.target_ticket_id else None,
            "thread_id": str(self.thread_id) if self.thread_id else None,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class IntakePromotionCommand:
    """Promote one prior inbound event to exactly one ticket provenance edge."""

    client_command_id: UUID
    inbound_event_id: UUID
    expected_thread_version: int
    intent: IntakeIntent
    initial_custodian_id: UUID | None = None
    priority: str | None = None
    title: str | None = None
    target_ticket_id: UUID | None = None
    expected_ticket_version: int | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_thread_version": self.expected_thread_version,
            "expected_ticket_version": self.expected_ticket_version,
            "inbound_event_id": str(self.inbound_event_id),
            "initial_custodian_id": (
                str(self.initial_custodian_id) if self.initial_custodian_id else None
            ),
            "intent": self.intent.value,
            "priority": self.priority,
            "target_ticket_id": str(self.target_ticket_id) if self.target_ticket_id else None,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class IntakeCommandResult:
    """Committed result retained byte-for-byte for replay and durability overlay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    inbound_event_id: UUID
    outcome: IntakeOutcome
    project_key: str
    source: InboundSource
    thread_id: UUID
    thread_version: int
    ticket_id: UUID | None = None
    ticket_version: int | None = None
    request_id: UUID | None = None
    request_number: int | None = None
    quarantine_reason: str | None = None

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "inbound_event_id": str(self.inbound_event_id),
            "outcome": self.outcome.value,
            "project_key": self.project_key,
            "quarantine_reason": self.quarantine_reason,
            "source": asdict(self.source),
            "thread_id": str(self.thread_id),
            "thread_version": self.thread_version,
            "ticket_id": str(self.ticket_id) if self.ticket_id else None,
            "ticket_version": self.ticket_version,
            "request_id": str(self.request_id) if self.request_id else None,
            "request_number": self.request_number,
        }
