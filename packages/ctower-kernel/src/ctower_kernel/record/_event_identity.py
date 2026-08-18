"""Cross-event aggregate identity validation for Record envelopes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ctower_kernel.record.bootstrap_events import BootstrapCreatedPayload
from ctower_kernel.record.catalog_events import (
    CatalogBundleActivatedPayload,
    CatalogComponentPublishedPayload,
)
from ctower_kernel.record.credentials import (
    SeatCredentialIssuedPayload,
    SeatCredentialRevokedPayload,
)
from ctower_kernel.record.dream_dispatch_events import validate_dream_runtime_identity
from ctower_kernel.record.inbox_events import _validate_identity as _validate_inbox_identity
from ctower_kernel.record.intake_events import _validate_identity as _validate_intake_identity
from ctower_kernel.record.knowledge_events import _validate_identity as _validate_knowledge_identity
from ctower_kernel.record.poison_events import PoisonDispositionRecordedPayload
from ctower_kernel.record.request_events import _validate_identity as _validate_request_identity
from ctower_kernel.record.request_proposal_events import (
    _validate_identity as _validate_request_proposal_identity,
)
from ctower_kernel.record.routine_events import validate_routine_retirement_identity
from ctower_kernel.record.ruling_events import _validate_identity as _validate_ruling_identity
from ctower_kernel.record.session_events import (
    SessionClosedPayload,
    SessionStartedPayload,
    SessionTransitionedPayload,
)
from ctower_kernel.record.spawn_events import SpawnRecordedPayload, SpawnTransitionedPayload
from ctower_kernel.record.ticket_events import TicketCommentAddedPayload

if TYPE_CHECKING:
    from ctower_kernel.record.events import EventEnvelope

__all__: tuple[str, ...] = ()


def validate_event_identity(
    event: EventEnvelope,
    expected_stream_id: str,
    occurrence_type: type[object],
) -> None:
    if event.stream_id != expected_stream_id:
        raise ValueError("event stream does not match its kind and aggregate identity")
    _validate_bootstrap_identity(event)
    _validate_ticket_identity(event)
    _validate_catalog_identity(event)
    _validate_occurrence_identity(event, occurrence_type)
    validate_routine_retirement_identity(event.aggregate_id, event.payload)
    validate_dream_runtime_identity(event.aggregate_id, event.payload)
    _validate_poison_identity(event)
    _validate_intake_identity(event.payload, event.stream_id, event.aggregate_id)
    _validate_inbox_identity(event.payload, event.aggregate_id)
    _validate_knowledge_identity(event.payload, event.aggregate_id)
    _validate_request_identity(event.payload, event.aggregate_id)
    _validate_request_proposal_identity(event.payload, event.aggregate_id)
    _validate_ruling_identity(event.payload, event.aggregate_id)
    _validate_seat_credential_identity(event)
    _validate_session_identity(event)
    _validate_spawn_identity(event)


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


def _validate_occurrence_identity(event: EventEnvelope, occurrence_type: type[object]) -> None:
    if isinstance(event.payload, occurrence_type) and (
        event.aggregate_id != cast(Any, event.payload).occurrence_id
    ):
        raise ValueError("Routine aggregate and occurrence identity must match")


def _validate_poison_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, PoisonDispositionRecordedPayload) and (
        event.aggregate_id != event.client_command_id
    ):
        raise ValueError("poison disposition aggregate must be its command identity")


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


def _validate_spawn_identity(event: EventEnvelope) -> None:
    if isinstance(event.payload, SpawnRecordedPayload | SpawnTransitionedPayload) and (
        event.aggregate_id != event.payload.spawn_id
    ):
        raise ValueError("spawn aggregate and payload identity must match")
