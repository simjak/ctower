from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from ctower_kernel.record.comments import TicketCommentCommand, ticket_accepts_comments
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    TicketCommentAddedPayload,
    canonical_event_bytes,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.interface import TimelineEvent

_ACTOR_ID = UUID("00000000-0000-4000-8000-000000000001")
_COMMAND_ID = UUID("00000000-0000-4000-8000-000000000002")
_COMMENT_ID = UUID("00000000-0000-4000-8000-000000000003")
_EVENT_ID = UUID("00000000-0000-4000-8000-000000000004")
_TICKET_ID = UUID("00000000-0000-4000-8000-000000000005")
_TENANT_ID = UUID("00000000-0000-4000-8000-000000000006")
_NOW = datetime(2026, 7, 24, tzinfo=UTC)


def test_comment_is_a_strict_canonical_ticket_event_without_mutable_state() -> None:
    command = TicketCommentCommand(
        client_command_id=_COMMAND_ID,
        ticket_id=_TICKET_ID,
        body="Independent evidence is attached.",
    )
    payload = TicketCommentAddedPayload(
        body=command.body,
        comment_id=_COMMENT_ID,
        ticket_id=_TICKET_ID,
    )
    event = EventEnvelope(
        actor_principal_id=_ACTOR_ID,
        aggregate_id=_TICKET_ID,
        causation_id=None,
        client_command_id=_COMMAND_ID,
        correlation_id=_COMMAND_ID,
        event_id=_EVENT_ID,
        kind=EventKind.TICKET_COMMENT_ADDED,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=bytes.fromhex("1" * 64),
        sequence=2,
        server_time=_NOW,
        stream_id=f"ticket:{_TICKET_ID}",
        tenant_id=_TENANT_ID,
    )
    timeline = TimelineEvent(
        actor_principal_id=_ACTOR_ID,
        command_id=_COMMAND_ID,
        event_id=_EVENT_ID,
        kind=EventKind.TICKET_COMMENT_ADDED,
        occurred_at=_NOW,
        payload=payload,
        sequence=2,
    )

    assert command.request_payload() == {
        "body": "Independent evidence is attached.",
        "ticket_id": str(_TICKET_ID),
    }
    assert b"Independent evidence is attached." in canonical_event_bytes(event)
    assert timeline.response_payload()["kind"] == "ticket.comment_added"
    assert (
        ticket_payload_from_mapping(EventKind.TICKET_COMMENT_ADDED, payload.to_mapping()) == payload
    )


@pytest.mark.parametrize("body", ["", "   ", "x" * 4001])
def test_comment_body_rejects_empty_or_unbounded_content(body: str) -> None:
    with pytest.raises(ValueError, match="comment body"):
        TicketCommentCommand(
            client_command_id=_COMMAND_ID,
            ticket_id=_TICKET_ID,
            body=body,
        )


@pytest.mark.parametrize("state", ["closed", "cancelled"])
def test_comment_refuses_every_terminal_ticket_state(state: str) -> None:
    assert ticket_accepts_comments(state) is False


def test_comment_allows_non_terminal_ticket_state() -> None:
    assert ticket_accepts_comments("active") is True


def test_comment_event_refuses_mismatched_ticket_identity() -> None:
    with pytest.raises(ValueError, match="comment aggregate"):
        EventEnvelope(
            actor_principal_id=_ACTOR_ID,
            aggregate_id=UUID("00000000-0000-4000-8000-000000000099"),
            causation_id=None,
            client_command_id=_COMMAND_ID,
            correlation_id=_COMMAND_ID,
            event_id=_EVENT_ID,
            kind=EventKind.TICKET_COMMENT_ADDED,
            origin=EventOrigin.API,
            payload=TicketCommentAddedPayload(
                body="Visible comment",
                comment_id=_COMMENT_ID,
                ticket_id=_TICKET_ID,
            ),
            prev_hash=bytes(32),
            request_sha256=bytes.fromhex("1" * 64),
            sequence=2,
            server_time=_NOW,
            stream_id="ticket:00000000-0000-4000-8000-000000000099",
            tenant_id=_TENANT_ID,
        )
