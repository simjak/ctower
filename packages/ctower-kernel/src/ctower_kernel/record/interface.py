"""Small public Interface for atomic Record commands."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from ctower_kernel.record.comments import TicketCommentCommand, TicketCommentResult
from ctower_kernel.record.events import (
    CustodyTransferredPayload,
    EventKind,
    TicketCommentAddedPayload,
    TicketCreatedPayload,
    TicketEventPayload,
)
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakePromotionCommand,
    IntakeSubmitCommand,
)
from ctower_kernel.telemetry import TelemetryContext

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_RETRY_SECONDS = 60

__all__ = [
    "Actor",
    "AuditEvent",
    "AuditPage",
    "BootstrapCommand",
    "BootstrapReceipt",
    "CustodyCommand",
    "DurabilityDecision",
    "DurabilityFinalizationBatch",
    "DurabilityFinalizer",
    "DurabilityHealth",
    "DurabilityHealthStatus",
    "DurabilityReason",
    "DurabilityState",
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
    MIGRATION_IMPORTER = "migration_importer"
    FENCE_OBSERVER = "fence_observer"


class DurabilityState(StrEnum):
    """Only the monotonic wire states allowed for a committed command."""

    PENDING = "durability_pending"
    ACCEPTED = "accepted"


type DurabilityReason = Literal[
    "policy_pending_only",
    "standby_unconfigured",
    "standby_not_ready",
    "target_mismatch",
    "replay_missing",
    "integrity_mismatch",
    "receipt_pending",
    "standby_receipt_proven",
    "commit_ambiguous",
]


@dataclass(frozen=True, slots=True)
class DurabilityDecision:
    """Record-owned answer about one exact semantic command result."""

    command_id: UUID
    state: DurabilityState
    reason: DurabilityReason
    policy_ref: str
    command_root: str
    acceptance_position: int | None
    retry_after_seconds: int

    def __post_init__(self) -> None:
        if self.state is DurabilityState.ACCEPTED and self.acceptance_position is None:
            raise ValueError("accepted durability requires an acceptance position")
        if self.state is DurabilityState.PENDING and self.acceptance_position is not None:
            raise ValueError("pending durability cannot carry an acceptance position")
        if _SHA256_PATTERN.fullmatch(self.command_root) is None:
            raise ValueError("command root must be one SHA-256 digest")
        if self.acceptance_position is not None and self.acceptance_position < 1:
            raise ValueError("acceptance position must be positive")
        if not 1 <= self.retry_after_seconds <= _MAX_RETRY_SECONDS:
            raise ValueError("durability retry interval must be between 1 and 60 seconds")

    @property
    def accepted(self) -> bool:
        """Whether this command has an immutable accepted-order receipt."""

        return self.state is DurabilityState.ACCEPTED


class DurabilityHealthStatus(StrEnum):
    """Fail-closed state of the Record durability authority."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STATE_UNKNOWN = "STATE_UNKNOWN"


@dataclass(frozen=True, slots=True)
class DurabilityHealth:
    """Small Record health snapshot without operations-loop concerns."""

    status: DurabilityHealthStatus
    policy_ref: str
    target_identity: str
    acceptance_position: int | None
    observed_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class DurabilityFinalizationBatch:
    """One bounded ordinary-finalizer observation."""

    attempted: int
    accepted: int
    pending: int
    refused: int

    def __post_init__(self) -> None:
        values = (self.attempted, self.accepted, self.pending, self.refused)
        if any(value < 0 for value in values):
            raise ValueError("durability finalizer counts cannot be negative")
        if self.attempted != self.accepted + self.pending + self.refused:
            raise ValueError("durability finalizer counts must conserve attempts")


class DurabilityFinalizer(Protocol):
    """Small maintenance Interface for ordinary pending-command reconciliation."""

    def finalize_pending(self, *, limit: int = 100) -> DurabilityFinalizationBatch: ...


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
    principal_id: UUID
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
    durability_state: DurabilityState = DurabilityState.PENDING

    def response_payload(self) -> dict[str, object]:
        """Return the generated HTTP resource shape."""

        return {
            "created_at": self.created_at.isoformat(),
            "custodian_id": str(self.custodian_id),
            "durability_state": self.durability_state.value,
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
            EventKind.TICKET_COMMENT_ADDED: TicketCommentAddedPayload,
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

    def submit_intake(
        self,
        actor: Actor,
        command: IntakeSubmitCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem:
        """Atomically record one inbound event and its explicit initial intent."""

        ...

    def promote_intake(
        self,
        actor: Actor,
        command: IntakePromotionCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult | RecordProblem:
        """Atomically attach one unlinked inbound event to exactly one ticket."""

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

    def add_comment(
        self,
        actor: Actor,
        command: TicketCommentCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> TicketCommentResult | RecordProblem:
        """Append or exactly replay one authenticated ticket comment."""

        ...

    def reconcile_durability(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        *,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> DurabilityDecision | RecordProblem:
        """Prove or conservatively defer off-host acceptance for one command."""

        ...

    def durability_health(self, *, now: datetime) -> DurabilityHealth:
        """Report the current named-target durability state without false green."""

        ...
