"""Production Atom rendering tests for the movement feed."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import feedparser  # type: ignore[import-untyped]

from ctower_api import _project_feed_atom_routes as routes
from ctower_kernel.record.movement_events import MovementEvent

__all__: tuple[str, ...] = ()

_EVENT = MovementEvent(
    event_id=UUID("00000000-0000-7000-8000-000000000001"),
    record_position=12,
    ticket_id=UUID("00000000-0000-7000-8000-000000000002"),
    from_stage="capture",
    to_stage="frame",
    evaluation_ref="00000000-0000-7000-8000-000000000003",
    workflow_ref="fixture.workflow@1",
    workflow_version=2,
    occurred_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
)


def test_atom_entry_has_stable_identity_timestamp_and_authorized_ticket_link() -> None:
    parsed = feedparser.parse(
        routes._atom_document(
            (_EVENT,),
            "ctower",
            cursor=0,
            limit=1,
            next_cursor=None,
        )
    )

    assert parsed.bozo is False
    entry = parsed.entries[0]
    assert entry.id == f"urn:uuid:{_EVENT.event_id}"
    assert entry.updated == "2026-08-09T12:00:00Z"
    assert any(
        link.rel == "alternate" and link.href == f"/v1/tickets/{_EVENT.ticket_id}/timeline"
        for link in entry.links
    )
    assert "ticket text" not in str(entry)


def test_atom_pagination_names_the_same_record_position_cursor() -> None:
    parsed = feedparser.parse(
        routes._atom_document(
            (_EVENT,),
            "ctower",
            cursor=7,
            limit=1,
            next_cursor=12,
        )
    )

    assert parsed.bozo is False
    assert {link.rel for link in parsed.feed.links} == {"self", "next"}
    assert {link.rel: link.href for link in parsed.feed.links} == {
        "self": "/v1/projects/ctower/movement.atom?cursor=7&limit=1",
        "next": "/v1/projects/ctower/movement.atom?cursor=12&limit=1",
    }


def test_empty_atom_feed_has_a_deterministic_updated_timestamp() -> None:
    parsed = feedparser.parse(
        routes._atom_document((), "ctower", cursor=0, limit=50, next_cursor=None)
    )

    assert parsed.bozo is False
    assert parsed.feed.updated == "1970-01-01T00:00:00Z"
    assert parsed.entries == []
