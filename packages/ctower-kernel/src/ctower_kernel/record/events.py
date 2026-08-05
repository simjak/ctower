"""Typed Record authority for canonical event envelopes and hashes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from ctower_kernel.record.catalog_events import (
    CatalogBundleActivatedPayload,
    CatalogComponentPublishedPayload,
    CatalogComponentReference,
    CatalogEventPayload,
)
from ctower_kernel.record.credentials import (
    SeatCredentialIssuedPayload,
    SeatCredentialRevokedPayload,
)
from ctower_kernel.record.intake_events import (
    InboundEventPromotedPayload,
    InboundEventRecordedPayload,
    IntakeEventPayload,
)
from ctower_kernel.record.migration_events import MigrationChangedPayload
from ctower_kernel.record.session_events import (
    SessionClosedPayload,
    SessionEventPayload,
    SessionStartedPayload,
    SessionTransitionedPayload,
)
from ctower_kernel.record.ticket_events import (
    CustodyTransferredPayload,
    TicketCommentAddedPayload,
    TicketCreatedPayload,
    TicketEventPayload,
)
from ctower_kernel.record.ticket_events import (
    ticket_payload_from_mapping as _ticket_payload_from_mapping,
)
from ctower_kernel.record.work_events import WorkChangedPayload

__all__ = [
    "BootstrapCreatedPayload",
    "CatalogBundleActivatedPayload",
    "CatalogComponentPublishedPayload",
    "CatalogComponentReference",
    "CatalogEventPayload",
    "CustodyTransferredPayload",
    "EventEnvelope",
    "EventKind",
    "EventOrigin",
    "InboundEventPromotedPayload",
    "InboundEventRecordedPayload",
    "IntakeEventPayload",
    "MigrationChangedPayload",
    "PoisonDispositionRecordedPayload",
    "ProofChangedPayload",
    "RoutineOccurrenceRecordedPayload",
    "TicketCommentAddedPayload",
    "TicketCreatedPayload",
    "TicketEventPayload",
    "WorkChangedPayload",
    "WorkflowChangedPayload",
    "canonical_event_bytes",
    "event_catalog",
    "event_digest",
    "ticket_payload_from_mapping",
]


class EventKind(StrEnum):
    BOOTSTRAP_CREATED = "bootstrap.first_tenant_created"
    TICKET_CREATED = "ticket.created"
    CUSTODY_TRANSFERRED = "ticket.custody_transferred"
    TICKET_COMMENT_ADDED = "ticket.comment_added"
    CATALOG_COMPONENT_PUBLISHED = "catalog.component_published"
    CATALOG_BUNDLE_ACTIVATED = "catalog.bundle_activated"
    PROOF_CHANGED = "proof.changed"
    WORKFLOW_CHANGED = "workflow.changed"
    WORK_CHANGED = "work.changed"
    ROUTINE_OCCURRENCE_RECORDED = "routine.occurrence_recorded"
    POISON_DISPOSITION_RECORDED = "attention.poison_disposition_recorded"
    MIGRATION_CHANGED = "migration.changed"
    INBOUND_EVENT_RECORDED = "intake.inbound_event_recorded"
    INBOUND_EVENT_PROMOTED = "intake.inbound_event_promoted"
    SEAT_CREDENTIAL_ISSUED = "access.seat_credential_issued"
    SEAT_CREDENTIAL_REVOKED = "access.seat_credential_revoked"
    SESSION_STARTED = "session.started"
    SESSION_TRANSITIONED = "session.transitioned"
    SESSION_CLOSED = "session.closed"


class EventOrigin(StrEnum):
    API = "api"
    BOOTSTRAP = "bootstrap"
    CONTROL_WORKER = "control_worker"
    MIGRATION_IMPORTER = "migration_importer"


_DIGEST_BYTES = 32
_MAX_UTC_OFFSET_SECONDS = 64800
_DIGEST_TEXT = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_VERSIONED_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class BootstrapCreatedPayload:
    commander_id: UUID
    commander_vault_ref: str
    operator_credential_ref: str
    operator_id: UUID
    operator_vault_ref: str
    tenant_id: UUID
    tenant_slug: str

    def __post_init__(self) -> None:
        _require_uuid_fields(
            self,
            ("commander_id", "operator_id", "tenant_id"),
        )
        _bounded("commander_vault_ref", self.commander_vault_ref, minimum=1)
        _bounded("operator_credential_ref", self.operator_credential_ref, minimum=1)
        _bounded("operator_vault_ref", self.operator_vault_ref, minimum=1)
        _bounded("tenant_slug", self.tenant_slug, minimum=2, maximum=63)

    def to_mapping(self) -> dict[str, object]:
        return {
            "commander_id": str(self.commander_id),
            "commander_vault_ref": self.commander_vault_ref,
            "operator_credential_ref": self.operator_credential_ref,
            "operator_id": str(self.operator_id),
            "operator_vault_ref": self.operator_vault_ref,
            "tenant_id": str(self.tenant_id),
            "tenant_slug": self.tenant_slug,
        }


@dataclass(frozen=True, slots=True)
class ProofChangedPayload:
    operation: str
    ticket_id: UUID
    proof_version: int
    candidate_digest: str
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("ticket_id",))
        _require_uuid_tuple("invalidated_evidence_ids", self.invalidated_evidence_ids)
        _require_uuid_tuple("invalidated_verdict_ids", self.invalidated_verdict_ids)
        if self.operation not in {
            "freeze_criteria",
            "record_evidence",
            "record_verdict",
            "change_candidate",
        }:
            raise ValueError("proof operation is outside the authored event contract")
        if self.proof_version < 1:
            raise ValueError("proof version must be positive")
        if _DIGEST_TEXT.fullmatch(self.candidate_digest) is None:
            raise ValueError("candidate digest must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "invalidated_evidence_ids": [str(item) for item in self.invalidated_evidence_ids],
            "invalidated_verdict_ids": [str(item) for item in self.invalidated_verdict_ids],
            "operation": self.operation,
            "proof_version": self.proof_version,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class WorkflowChangedPayload:
    operation: str
    ticket_id: UUID
    workflow_ref: str
    workflow_version: int
    stage: str
    lifecycle_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("ticket_id",))
        if self.operation not in {"start", "transition", "resolve_close"}:
            raise ValueError("workflow operation is outside the authored event contract")
        if self.workflow_version < 1:
            raise ValueError("workflow version must be positive")
        if _VERSIONED_REFERENCE.fullmatch(self.workflow_ref) is None:
            raise ValueError("workflow reference must be versioned")
        if _STABLE_KEY.fullmatch(self.stage) is None:
            raise ValueError("workflow stage must be stable")
        if self.lifecycle_facts not in {(), ("resolved", "closed")}:
            raise ValueError("workflow lifecycle facts must preserve terminal order")

    def to_mapping(self) -> dict[str, object]:
        return {
            "lifecycle_facts": list(self.lifecycle_facts),
            "operation": self.operation,
            "stage": self.stage,
            "ticket_id": str(self.ticket_id),
            "workflow_ref": self.workflow_ref,
            "workflow_version": self.workflow_version,
        }


@dataclass(frozen=True, slots=True)
class RoutineOccurrenceRecordedPayload:
    occurrence_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    local_civil_time: str
    timezone: str
    utc_offset_seconds: int | None
    offset_decision: str
    outcome: str
    job_id: UUID | None

    def __post_init__(self) -> None:
        _validate_routine_occurrence_identity(self)
        _validate_routine_occurrence_decision(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "job_id": str(self.job_id) if self.job_id is not None else None,
            "local_civil_time": self.local_civil_time,
            "occurrence_id": str(self.occurrence_id),
            "offset_decision": self.offset_decision,
            "outcome": self.outcome,
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
            "scheduled_for": _timestamp(self.scheduled_for),
            "timezone": self.timezone,
            "utc_offset_seconds": self.utc_offset_seconds,
        }


def _validate_routine_occurrence_identity(payload: RoutineOccurrenceRecordedPayload) -> None:
    _require_uuid_fields(payload, ("occurrence_id",))
    if payload.job_id is not None and not isinstance(payload.job_id, UUID):
        raise TypeError("job_id must be a UUID or None")
    if _VERSIONED_REFERENCE.fullmatch(payload.routine_ref) is None:
        raise ValueError("routine reference must be versioned")
    if _DIGEST_TEXT.fullmatch(payload.revision_digest) is None:
        raise ValueError("routine revision must be content addressed")
    _validate_timestamp(payload.scheduled_for)
    _bounded("local_civil_time", payload.local_civil_time, minimum=1, maximum=32)
    _bounded("timezone", payload.timezone, minimum=1, maximum=128)


def _validate_routine_occurrence_decision(payload: RoutineOccurrenceRecordedPayload) -> None:
    offset = payload.utc_offset_seconds
    if offset is not None and not (-_MAX_UTC_OFFSET_SECONDS <= offset <= _MAX_UTC_OFFSET_SECONDS):
        raise ValueError("Routine UTC offset is outside the authored contract")
    if payload.offset_decision not in {"exact", "earlier_offset", "nonexistent_local_time"}:
        raise ValueError("Routine offset decision is outside the authored contract")
    if payload.outcome not in {"queued", "coalesced", "skipped", "refused"}:
        raise ValueError("Routine outcome is outside the authored contract")
    if payload.offset_decision == "nonexistent_local_time" and (
        offset is not None or payload.outcome != "skipped"
    ):
        raise ValueError("nonexistent Routine civil time must be visibly skipped")
    if (payload.outcome == "queued") != (payload.job_id is not None):
        raise ValueError("only a queued Routine occurrence carries a fixed job")


@dataclass(frozen=True, slots=True)
class PoisonDispositionRecordedPayload:
    outbox_id: UUID
    consumer_key: str
    topic: str
    action: str
    reason: str

    def __post_init__(self) -> None:
        _require_uuid_fields(self, ("outbox_id",))
        if _STABLE_KEY.fullmatch(self.consumer_key) is None:
            raise ValueError("poison consumer key is outside the authored event contract")
        if _STABLE_KEY.fullmatch(self.topic) is None:
            raise ValueError("poison topic is outside the authored event contract")
        if self.action not in {"retry", "tombstone"}:
            raise ValueError("poison action is outside the authored event contract")
        _bounded("reason", self.reason, minimum=1, maximum=500)

    def to_mapping(self) -> dict[str, object]:
        return {
            "action": self.action,
            "consumer_key": self.consumer_key,
            "outbox_id": str(self.outbox_id),
            "reason": self.reason,
            "topic": self.topic,
        }


type EventPayload = (
    BootstrapCreatedPayload
    | CatalogComponentPublishedPayload
    | CatalogBundleActivatedPayload
    | TicketCreatedPayload
    | CustodyTransferredPayload
    | TicketCommentAddedPayload
    | ProofChangedPayload
    | WorkflowChangedPayload
    | WorkChangedPayload
    | RoutineOccurrenceRecordedPayload
    | PoisonDispositionRecordedPayload
    | MigrationChangedPayload
    | IntakeEventPayload
    | SeatCredentialIssuedPayload
    | SeatCredentialRevokedPayload
    | SessionEventPayload
)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    actor_principal_id: UUID
    aggregate_id: UUID
    causation_id: UUID | None
    client_command_id: UUID
    correlation_id: UUID
    event_id: UUID
    kind: EventKind
    origin: EventOrigin
    payload: EventPayload
    prev_hash: bytes
    request_sha256: bytes
    sequence: int
    server_time: datetime
    stream_id: str
    tenant_id: UUID
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_variant(self)
        _validate_envelope_values(self)
        _validate_event_identity(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "actor_principal_id": str(self.actor_principal_id),
            "aggregate_id": str(self.aggregate_id),
            "causation_id": str(self.causation_id) if self.causation_id is not None else None,
            "client_command_id": str(self.client_command_id),
            "correlation_id": str(self.correlation_id),
            "event_id": str(self.event_id),
            "kind": self.kind.value,
            "origin": self.origin.value,
            "payload": self.payload.to_mapping(),
            "prev_hash": f"sha256:{self.prev_hash.hex()}",
            "request_sha256": f"sha256:{self.request_sha256.hex()}",
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "server_time": _timestamp(self.server_time),
            "stream_id": self.stream_id,
            "tenant_id": str(self.tenant_id),
        }


def canonical_event_bytes(event: EventEnvelope) -> bytes:
    """Render the event-domain JSON subset with RFC 8785 ordering and encoding."""

    if not isinstance(event, EventEnvelope):
        raise TypeError("event hashing requires a validated EventEnvelope")
    return _canonical(event.to_mapping()).encode("utf-8")


def event_digest(event: EventEnvelope) -> bytes:
    return hashlib.sha256(canonical_event_bytes(event)).digest()


def ticket_payload_from_mapping(
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    legacy_project_key: str | None = None,
) -> TicketEventPayload:
    """Rebuild one typed ticket payload at the persistence read boundary."""

    return _ticket_payload_from_mapping(
        kind.value,
        payload,
        legacy_project_key=legacy_project_key,
    )


@dataclass(frozen=True, slots=True)
class EventCatalogEntry:
    """One authoritative catalog row: the payload, stream, and origins a kind may use.

    This catalog is the single authority every derived kind set reads. A reader that
    needs "the session kinds" or "the stream prefix for a kind" derives it here rather
    than re-typing a second enum in API, CLI, SQL, browser, or test code; a kind added
    here with no authored contract branch fails the catalog/contract parity guard.
    """

    kind: EventKind
    payload_type: type[object]
    stream_prefix: str
    origins: frozenset[EventOrigin] = frozenset({EventOrigin.API})
    session_fact: bool = False
    project_feed: bool = False


_BOOTSTRAP = frozenset({EventOrigin.BOOTSTRAP})
_WORKER = frozenset({EventOrigin.CONTROL_WORKER})
_API_OR_IMPORT = frozenset({EventOrigin.API, EventOrigin.MIGRATION_IMPORTER})
_SESSION = "session"

# THE authoritative event catalog. Rows default to the API origin; a row states its
# origins only where the kind is also reachable from bootstrap, the control worker, or
# the migration importer.
_EVENT_CATALOG: dict[EventKind, EventCatalogEntry] = {
    entry.kind: entry
    for entry in (
        EventCatalogEntry(
            EventKind.BOOTSTRAP_CREATED, BootstrapCreatedPayload, "tenant", _BOOTSTRAP
        ),
        EventCatalogEntry(
            EventKind.TICKET_CREATED,
            TicketCreatedPayload,
            "ticket",
            _API_OR_IMPORT,
            project_feed=True,
        ),
        EventCatalogEntry(
            EventKind.CUSTODY_TRANSFERRED, CustodyTransferredPayload, "ticket", project_feed=True
        ),
        EventCatalogEntry(
            EventKind.TICKET_COMMENT_ADDED, TicketCommentAddedPayload, "ticket", project_feed=True
        ),
        EventCatalogEntry(
            EventKind.CATALOG_COMPONENT_PUBLISHED, CatalogComponentPublishedPayload, "catalog"
        ),
        EventCatalogEntry(
            EventKind.CATALOG_BUNDLE_ACTIVATED, CatalogBundleActivatedPayload, "catalog"
        ),
        EventCatalogEntry(EventKind.PROOF_CHANGED, ProofChangedPayload, "proof", project_feed=True),
        EventCatalogEntry(
            EventKind.WORKFLOW_CHANGED, WorkflowChangedPayload, "workflow", project_feed=True
        ),
        EventCatalogEntry(
            EventKind.WORK_CHANGED,
            WorkChangedPayload,
            "ticket",
            _API_OR_IMPORT,
            project_feed=True,
        ),
        EventCatalogEntry(
            EventKind.ROUTINE_OCCURRENCE_RECORDED,
            RoutineOccurrenceRecordedPayload,
            "routine-occurrence",
            _WORKER,
        ),
        EventCatalogEntry(
            EventKind.POISON_DISPOSITION_RECORDED,
            PoisonDispositionRecordedPayload,
            "poison-disposition",
        ),
        EventCatalogEntry(
            EventKind.MIGRATION_CHANGED, MigrationChangedPayload, "migration", _API_OR_IMPORT
        ),
        EventCatalogEntry(
            EventKind.INBOUND_EVENT_RECORDED, InboundEventRecordedPayload, "inbound-thread"
        ),
        EventCatalogEntry(
            EventKind.INBOUND_EVENT_PROMOTED, InboundEventPromotedPayload, "inbound-thread"
        ),
        EventCatalogEntry(
            EventKind.SEAT_CREDENTIAL_ISSUED, SeatCredentialIssuedPayload, "seat-credential"
        ),
        EventCatalogEntry(
            EventKind.SEAT_CREDENTIAL_REVOKED, SeatCredentialRevokedPayload, "seat-credential"
        ),
        EventCatalogEntry(
            EventKind.SESSION_STARTED, SessionStartedPayload, _SESSION, session_fact=True
        ),
        EventCatalogEntry(
            EventKind.SESSION_TRANSITIONED, SessionTransitionedPayload, _SESSION, session_fact=True
        ),
        EventCatalogEntry(
            EventKind.SESSION_CLOSED, SessionClosedPayload, _SESSION, session_fact=True
        ),
    )
}

if frozenset(_EVENT_CATALOG) != frozenset(EventKind):
    raise RuntimeError("the authoritative event catalog must cover every event kind exactly once")


def event_catalog() -> tuple[EventCatalogEntry, ...]:
    """Return the authoritative event catalog in its authored order.

    Every derived kind set — the envelope enum and union, the HTTP audit union, the
    generated clients, the CLI, and SQL — reads this and never re-types a second enum.
    Session membership is the `session_fact` column, so a reader asking for "the session
    kinds" filters this catalog rather than declaring its own list.
    """

    return tuple(_EVENT_CATALOG.values())


def project_event_kinds() -> tuple[EventKind, ...]:
    """Return the catalog-derived kind set exposed by the project-scoped event feed.

    Project-feed membership is the `project_feed` column, so a reader asking for "the
    project-feed kinds" filters this catalog rather than declaring its own list — a kind
    added here with no feed decision defaults to absent, never silently included.
    """

    return tuple(kind for kind, entry in _EVENT_CATALOG.items() if entry.project_feed)


def _validate_variant(event: EventEnvelope) -> None:
    if not isinstance(event.kind, EventKind) or not isinstance(event.origin, EventOrigin):
        raise TypeError("event kind and origin must use authored enums")
    entry = _EVENT_CATALOG[event.kind]
    if not isinstance(event.payload, entry.payload_type):
        raise TypeError(f"{event.kind} requires {entry.payload_type.__name__}")
    if event.origin not in entry.origins:
        raise ValueError(f"{event.kind} has an unauthorized origin")


def _validate_envelope_values(event: EventEnvelope) -> None:
    _require_uuid_fields(
        event,
        (
            "actor_principal_id",
            "aggregate_id",
            "client_command_id",
            "correlation_id",
            "event_id",
            "tenant_id",
        ),
    )
    if event.causation_id is not None and not isinstance(event.causation_id, UUID):
        raise TypeError("causation_id must be a UUID or None")
    _validate_sequence(event)
    _validate_digest("prev_hash", event.prev_hash)
    _validate_digest("request_sha256", event.request_sha256)
    _validate_timestamp(event.server_time)


def _validate_sequence(event: EventEnvelope) -> None:
    if type(event.sequence) is not int or type(event.schema_version) is not int:
        raise TypeError("event sequence and schema version must be integers")
    if event.sequence < 1 or event.schema_version != 1:
        raise ValueError("event sequence and schema version are outside the authored contract")


def _validate_digest(label: str, value: object) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{label} must be bytes")
    if len(value) != _DIGEST_BYTES:
        raise ValueError(f"{label} must contain exactly 32 bytes")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("event timestamps must be datetimes")
    if value.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")


def _validate_event_identity(event: EventEnvelope) -> None:
    if event.stream_id != _stream_id(event.kind, event.aggregate_id):
        raise ValueError("event stream does not match its kind and aggregate identity")
    _validate_bootstrap_identity(event)
    _validate_ticket_identity(event)
    _validate_catalog_identity(event)
    _validate_occurrence_identity(event)
    _validate_poison_identity(event)
    _validate_intake_identity(event)
    _validate_seat_credential_identity(event)
    _validate_session_identity(event)


def _validate_bootstrap_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, BootstrapCreatedPayload) and (
        event.aggregate_id != event.tenant_id or event.payload.tenant_id != event.tenant_id
    ):
        raise ValueError("bootstrap aggregate, payload, and tenant identity must match")


def _validate_ticket_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, TicketCommentAddedPayload) and (
        event.aggregate_id != event.payload.ticket_id
    ):
        raise ValueError("comment aggregate and ticket identity must match")


def _validate_catalog_identity(event: EventEnvelope) -> None:
    if (
        isinstance(event.payload, CatalogComponentPublishedPayload | CatalogBundleActivatedPayload)
        and event.aggregate_id != event.tenant_id
    ):
        raise ValueError("Catalog aggregate and tenant identity must match")


def _validate_occurrence_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, RoutineOccurrenceRecordedPayload) and (
        event.aggregate_id != event.payload.occurrence_id
    ):
        raise ValueError("Routine aggregate and occurrence identity must match")


def _validate_poison_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, PoisonDispositionRecordedPayload) and (
        event.aggregate_id != event.client_command_id
    ):
        raise ValueError("poison disposition aggregate must be its command identity")


def _validate_intake_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, InboundEventRecordedPayload | InboundEventPromotedPayload) and (
        event.stream_id != f"inbound-thread:{event.aggregate_id}"
    ):
        raise ValueError("intake event must use its inbound thread stream")


def _validate_seat_credential_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, SeatCredentialIssuedPayload | SeatCredentialRevokedPayload) and (
        event.aggregate_id != event.payload.credential_id
    ):
        raise ValueError("seat credential aggregate and payload identity must match")


def _validate_session_identity(event: EventEnvelope) -> None:
    if (
        isinstance(
            event.payload,
            SessionStartedPayload | SessionTransitionedPayload | SessionClosedPayload,
        )
        and event.aggregate_id != event.payload.session_id
    ):
        raise ValueError("session aggregate and payload identity must match")


def _stream_id(kind: EventKind, aggregate_id: UUID) -> str:
    if kind is EventKind.BOOTSTRAP_CREATED:
        return f"tenant:{aggregate_id}:bootstrap"
    return f"{_EVENT_CATALOG[kind].stream_prefix}:{aggregate_id}"


def _bounded(label: str, value: object, *, minimum: int, maximum: int | None = None) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise ValueError(f"{label} is outside the authored event contract")


def _require_uuid_fields(value: object, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(getattr(value, name), UUID):
            raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, UUID) for item in value):
        raise TypeError(f"{label} must be a UUID tuple")


def _canonical(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        items = sorted(value.items(), key=lambda item: item[0].encode("utf-16be"))
        return "{" + ",".join(f"{_canonical(key)}:{_canonical(item)}" for key, item in items) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    raise TypeError(f"unsupported canonical event value: {type(value).__name__}")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
