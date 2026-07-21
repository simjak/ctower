"""Small public Interface for atomic Record commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.record.events import (
    CustodyTransferredPayload,
    EventKind,
    TicketCreatedPayload,
    TicketEventPayload,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = [
    "Actor",
    "AuditEvent",
    "AuditPage",
    "BootstrapCommand",
    "BootstrapReceipt",
    "CustodyCommand",
    "PrincipalKind",
    "Record",
    "RecordProblem",
    "SourceReference",
    "Ticket",
    "TicketCommand",
    "TicketCommandResult",
    "TicketTimeline",
    "TimelineEvent",
]


class PrincipalKind(StrEnum):
    """Principal kinds allowed by this walking slice."""

    OPERATOR = "operator"
    COMMANDER = "commander"


@dataclass(frozen=True, slots=True)
class Actor:
    """Authenticated tenant authority resolved from a credential digest."""

    principal_id: UUID
    tenant_id: UUID
    kind: PrincipalKind


@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    """Validated first-tenant values entering the trusted kernel."""

    client_command_id: UUID
    commander_name: str
    commander_vault_ref: str
    operator_credential_ref: str
    operator_name: str
    operator_vault_ref: str
    tenant_name: str
    tenant_slug: str

    def request_payload(self) -> dict[str, str]:
        """Return the cross-process body without transport authority."""

        payload = asdict(self)
        payload.pop("client_command_id")
        return {str(key): str(value) for key, value in payload.items()}


@dataclass(frozen=True, slots=True)
class BootstrapReceipt:
    """Committed first-tenant receipt returned on success and exact replay."""

    command_id: UUID
    commander_id: UUID
    event_ids: tuple[UUID, ...]
    operator_id: UUID
    receipt_digest: str
    tenant_id: UUID

    def response_payload(self) -> dict[str, object]:
        """Return the exact authoritative HTTP response shape."""

        return {
            "command_id": str(self.command_id),
            "commander_id": str(self.commander_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "operator_id": str(self.operator_id),
            "receipt_digest": self.receipt_digest,
            "tenant_id": str(self.tenant_id),
        }


@dataclass(frozen=True, slots=True)
class RecordProblem:
    """Stable RFC 9457 failure with no partial Record mutation."""

    code: str
    detail: str
    status: int
    title: str
    command_id: UUID | None = None
    current_version: int | None = None
    unmet_facts: tuple[str, ...] = ()

    def response_payload(self) -> dict[str, object]:
        """Return a minimal RFC 9457 object."""

        payload: dict[str, object] = {
            "code": self.code,
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
            "type": f"https://ctower.dev/problems/{self.code}",
        }
        if self.command_id is not None:
            payload["command_id"] = str(self.command_id)
        if self.current_version is not None:
            payload["current_version"] = self.current_version
        if self.unmet_facts:
            payload["unmet_facts"] = list(self.unmet_facts)
        return payload


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Durable origin of a captured ticket."""

    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class TicketCommand:
    """Validated request to create one actionable ticket."""

    client_command_id: UUID
    initial_custodian_id: UUID
    priority: str
    source: SourceReference
    title: str

    def request_payload(self) -> dict[str, object]:
        """Return the request body without transport authority."""

        return {
            "initial_custodian_id": str(self.initial_custodian_id),
            "priority": self.priority,
            "source": asdict(self.source),
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class CustodyCommand:
    """Validated version-checked request to transfer accountable custody."""

    client_command_id: UUID
    expected_version: int
    from_custodian_id: UUID
    protected_transfer: bool
    reason: str
    ticket_id: UUID
    to_custodian_id: UUID

    def request_payload(self) -> dict[str, object]:
        """Return the complete command body used for idempotency."""

        return {
            "expected_version": self.expected_version,
            "from_custodian_id": str(self.from_custodian_id),
            "protected_transfer": self.protected_transfer,
            "reason": self.reason,
            "ticket_id": str(self.ticket_id),
            "to_custodian_id": str(self.to_custodian_id),
        }


@dataclass(frozen=True, slots=True)
class Ticket:
    """Current authoritative ticket resource."""

    ticket_id: UUID
    title: str
    source: SourceReference
    priority: str
    custodian_id: UUID
    version: int
    created_at: datetime

    def response_payload(self) -> dict[str, object]:
        """Return the generated HTTP resource shape."""

        return {
            "created_at": self.created_at.isoformat(),
            "custodian_id": str(self.custodian_id),
            "durability_state": "durability_pending",
            "priority": self.priority,
            "source": asdict(self.source),
            "ticket_id": str(self.ticket_id),
            "title": self.title,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class TicketCommandResult:
    """Committed ticket command result retained for exact replay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    ticket: Ticket

    def response_payload(self) -> dict[str, object]:
        """Return the exact authoritative command response."""

        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "ticket": self.ticket.response_payload(),
        }


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One ordered ticket event for the thin timeline."""

    actor_principal_id: UUID
    command_id: UUID
    event_id: UUID
    kind: EventKind
    occurred_at: datetime
    payload: TicketEventPayload
    sequence: int

    def __post_init__(self) -> None:
        expected_payload = {
            EventKind.TICKET_CREATED: TicketCreatedPayload,
            EventKind.CUSTODY_TRANSFERRED: CustodyTransferredPayload,
        }.get(self.kind)
        if expected_payload is None:
            raise ValueError("timeline kind must be a ticket event")
        if not isinstance(self.payload, expected_payload):
            raise TypeError(f"{self.kind} requires {expected_payload.__name__}")

    def response_payload(self) -> dict[str, object]:
        """Return the generated timeline event shape."""

        return {
            "actor_principal_id": str(self.actor_principal_id),
            "command_id": str(self.command_id),
            "event_id": str(self.event_id),
            "kind": self.kind.value,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload.to_mapping(),
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class TicketTimeline:
    """Ordered authoritative history for one tenant-scoped ticket."""

    ticket_id: UUID
    events: tuple[TimelineEvent, ...]

    def response_payload(self) -> dict[str, object]:
        """Return the generated timeline response shape."""

        return {
            "durability_state": "durability_pending",
            "events": [item.response_payload() for item in self.events],
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One canonical event linked to a ticket without payload inspection."""

    actor_principal_id: UUID
    command_id: UUID
    event_hash: str
    event_id: UUID
    kind: EventKind
    occurred_at: datetime
    payload: dict[str, object]
    record_position: int
    sequence: int
    stream_id: str

    def response_payload(self) -> dict[str, object]:
        return {
            "actor_principal_id": str(self.actor_principal_id),
            "command_id": str(self.command_id),
            "event_hash": self.event_hash,
            "event_id": str(self.event_id),
            "kind": self.kind.value,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
            "record_position": self.record_position,
            "sequence": self.sequence,
            "stream_id": self.stream_id,
        }


@dataclass(frozen=True, slots=True)
class AuditPage:
    """Stable global-position cursor page with no duplicate linked event."""

    ticket_id: UUID
    events: tuple[AuditEvent, ...]
    next_cursor: int | None

    def response_payload(self) -> dict[str, object]:
        return {
            "events": [event.response_payload() for event in self.events],
            "next_cursor": self.next_cursor,
            "ticket_id": str(self.ticket_id),
        }


class Record(Protocol):
    """Small atomic persistence authority consumed by Access and Work."""

    def authorize_bootstrap(
        self, capability_digest: bytes, *, origin: str, now: datetime
    ) -> RecordProblem | None:
        """Preauthorize raw bootstrap transport authority without mutation."""

        ...

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability_digest: bytes,
        request_digest: bytes,
        origin: str,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> BootstrapReceipt | RecordProblem:
        """Atomically commit or refuse one first-tenant command."""

        ...

    def actor_for_credential(self, credential_digest: bytes) -> Actor | None:
        """Resolve one active principal without exposing credential material."""

        ...

    def create_ticket(
        self,
        actor: Actor,
        command: TicketCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        """Atomically append or exactly replay one ticket creation."""

        ...

    def get_ticket(
        self, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
    ) -> Ticket | RecordProblem:
        """Read one tenant-scoped ticket without cross-tenant disclosure."""

        ...

    def ticket_timeline(
        self, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
    ) -> TicketTimeline | RecordProblem:
        """Read the ordered tenant-scoped event timeline."""

        ...

    def ticket_audit(
        self,
        actor: Actor,
        ticket_id: UUID,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> AuditPage | RecordProblem:
        """Read one cursor page from explicitly linked canonical events."""

        ...

    def transfer_custody(
        self,
        actor: Actor,
        command: CustodyCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommandResult | RecordProblem:
        """Atomically close and open the ticket's accountable custody interval."""

        ...
