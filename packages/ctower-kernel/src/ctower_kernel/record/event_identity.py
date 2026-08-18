"""Aggregate-identity checks shared by the canonical event envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ctower_kernel.record.bootstrap_events import BootstrapCreatedPayload
from ctower_kernel.record.catalog_events import (
    CatalogBundleActivatedPayload,
    CatalogComponentPublishedPayload,
)
from ctower_kernel.record.credentials import (
    SeatCredentialIssuedPayload,
    SeatCredentialRevokedPayload,
)
from ctower_kernel.record.poison_events import PoisonDispositionRecordedPayload
from ctower_kernel.record.session_events import (
    SessionClosedPayload,
    SessionStartedPayload,
    SessionTransitionedPayload,
)
from ctower_kernel.record.ticket_events import TicketCommentAddedPayload

if TYPE_CHECKING:
    from ctower_kernel.record.events import EventEnvelope


def validate_basic_event_identity(event: EventEnvelope) -> None:
    """Reject envelopes whose aggregate does not match their payload identity."""
    for validator in (
        _validate_bootstrap_identity,
        _validate_ticket_identity,
        _validate_catalog_identity,
        _validate_poison_identity,
        _validate_seat_credential_identity,
        _validate_session_identity,
    ):
        validator(event)


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
