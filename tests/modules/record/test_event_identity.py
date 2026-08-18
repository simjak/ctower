"""Coverage for cross-event aggregate identity refusals."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record._event_identity import (
    _validate_bootstrap_identity,
    _validate_catalog_identity,
    _validate_occurrence_identity,
    _validate_poison_identity,
    _validate_seat_credential_identity,
    _validate_session_identity,
    _validate_ticket_identity,
    validate_event_identity,
)
from ctower_kernel.record.bootstrap_events import BootstrapCreatedPayload
from ctower_kernel.record.catalog_events import CatalogComponentPublishedPayload
from ctower_kernel.record.credentials import SeatCredentialIssuedPayload
from ctower_kernel.record.dream_dispatch_events import DreamDispatchConsumedPayload
from ctower_kernel.record.events import RoutineOccurrenceRecordedPayload
from ctower_kernel.record.poison_events import PoisonDispositionRecordedPayload
from ctower_kernel.record.session_events import SessionStartedPayload
from ctower_kernel.record.ticket_events import TicketCommentAddedPayload

__all__: tuple[str, ...] = ()


def _unsafe(cls: type[object], **fields: object) -> object:
    value = object.__new__(cls)
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


def _event(
    payload: object,
    *,
    aggregate_id: UUID | None = None,
    tenant_id: UUID | None = None,
    client_command_id: UUID | None = None,
    stream_id: str = "expected",
) -> SimpleNamespace:
    return SimpleNamespace(
        payload=payload,
        aggregate_id=aggregate_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        client_command_id=client_command_id or uuid4(),
        stream_id=stream_id,
    )


def test_identity_dispatch_refuses_a_stream_mismatch_before_payload_checks() -> None:
    with pytest.raises(ValueError, match="stream"):
        validate_event_identity(_event(object(), stream_id="wrong"), "expected", object)


def test_identity_dispatch_refuses_each_local_aggregate_mismatch() -> None:
    tenant_id = uuid4()
    bootstrap = _unsafe(
        BootstrapCreatedPayload,
        tenant_id=tenant_id,
    )
    with pytest.raises(ValueError, match="bootstrap"):
        _validate_bootstrap_identity(_event(bootstrap, tenant_id=tenant_id))

    ticket = _unsafe(TicketCommentAddedPayload, ticket_id=uuid4())
    with pytest.raises(ValueError, match="comment"):
        _validate_ticket_identity(_event(ticket))

    catalog = _unsafe(CatalogComponentPublishedPayload)
    with pytest.raises(ValueError, match="Catalog"):
        _validate_catalog_identity(_event(catalog, tenant_id=tenant_id))

    occurrence_id = uuid4()
    occurrence = _unsafe(RoutineOccurrenceRecordedPayload, occurrence_id=occurrence_id)
    with pytest.raises(ValueError, match="Routine"):
        _validate_occurrence_identity(_event(occurrence), RoutineOccurrenceRecordedPayload)

    poison = _unsafe(PoisonDispositionRecordedPayload)
    with pytest.raises(ValueError, match="poison"):
        _validate_poison_identity(_event(poison))

    credential_id = uuid4()
    credential = _unsafe(SeatCredentialIssuedPayload, credential_id=credential_id)
    with pytest.raises(ValueError, match="credential"):
        _validate_seat_credential_identity(_event(credential))

    session_id = uuid4()
    session = _unsafe(SessionStartedPayload, session_id=session_id)
    with pytest.raises(ValueError, match="session"):
        _validate_session_identity(_event(session))


def test_identity_helpers_accept_non_matching_payload_variants() -> None:
    event = _event(DreamDispatchConsumedPayload)
    _validate_bootstrap_identity(event)
    _validate_ticket_identity(event)
    _validate_catalog_identity(event)
    _validate_occurrence_identity(event, RoutineOccurrenceRecordedPayload)
    _validate_poison_identity(event)
    _validate_seat_credential_identity(event)
    _validate_session_identity(event)
