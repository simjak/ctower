"""Strict canonical intake-event payload behavior."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.events import (
    InboundEventPromotedPayload,
    InboundEventRecordedPayload,
)

__all__: tuple[str, ...] = ()


def _recorded(**changes: object) -> InboundEventRecordedPayload:
    values: dict[str, object] = {
        "content_digest": "sha256:" + "0" * 64,
        "inbound_event_id": uuid4(),
        "intent": "discussion",
        "outcome": "discussion",
        "position": 1,
        "project_key": "ctower",
        "source_kind": "chat",
        "source_ref": "chat:message:1",
        "taint": "authenticated",
        "ticket_id": None,
    }
    values.update(changes)
    return InboundEventRecordedPayload(
        inbound_event_id=cast(UUID, values["inbound_event_id"]),
        source_kind=cast(str, values["source_kind"]),
        source_ref=cast(str, values["source_ref"]),
        project_key=cast(str, values["project_key"]),
        position=cast(int, values["position"]),
        intent=cast(str, values["intent"]),
        taint=cast(str, values["taint"]),
        outcome=cast(str, values["outcome"]),
        content_digest=cast(str, values["content_digest"]),
        ticket_id=cast(UUID | None, values["ticket_id"]),
    )


@pytest.mark.parametrize(
    "build",
    (
        lambda: _recorded(inbound_event_id="not-a-uuid"),
        lambda: _recorded(position=0),
        lambda: _recorded(intent="classify"),
        lambda: _recorded(taint="trusted"),
        lambda: _recorded(outcome="accepted"),
        lambda: _recorded(content_digest="sha256:short"),
        lambda: _recorded(project_key="X"),
        lambda: _recorded(source_kind=""),
        lambda: _recorded(source_ref="x" * 257),
        lambda: _recorded(outcome="ticket_created"),
        lambda: _recorded(ticket_id=uuid4()),
    ),
)
def test_recorded_payload_rejects_values_outside_the_contract(
    build: Callable[[], InboundEventRecordedPayload],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        build()


def test_recorded_payload_maps_the_explicit_ticket_edge() -> None:
    ticket_id = uuid4()
    payload = _recorded(
        intent="link_ticket",
        outcome="ticket_linked",
        ticket_id=ticket_id,
    )

    assert payload.to_mapping()["ticket_id"] == str(ticket_id)


def _promoted(**changes: object) -> InboundEventPromotedPayload:
    values: dict[str, object] = {
        "inbound_event_id": uuid4(),
        "intent": "create_ticket",
        "outcome": "ticket_created",
        "project_key": "ctower",
        "source_kind": "chat",
        "source_ref": "chat:message:1",
        "ticket_id": uuid4(),
    }
    values.update(changes)
    return InboundEventPromotedPayload(
        inbound_event_id=cast(UUID, values["inbound_event_id"]),
        source_kind=cast(str, values["source_kind"]),
        source_ref=cast(str, values["source_ref"]),
        project_key=cast(str, values["project_key"]),
        intent=cast(str, values["intent"]),
        outcome=cast(str, values["outcome"]),
        ticket_id=cast(UUID, values["ticket_id"]),
    )


@pytest.mark.parametrize(
    "build",
    (
        lambda: _promoted(inbound_event_id="not-a-uuid"),
        lambda: _promoted(ticket_id="not-a-uuid"),
        lambda: _promoted(source_kind=""),
        lambda: _promoted(intent="discussion"),
        lambda: _promoted(outcome="discussion"),
    ),
)
def test_promoted_payload_requires_one_actionable_ticket_edge(
    build: Callable[[], InboundEventPromotedPayload],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        build()


def test_promoted_payload_maps_immutable_source_provenance() -> None:
    payload = _promoted(intent="link_ticket", outcome="ticket_linked")

    assert payload.to_mapping()["source_ref"] == "chat:message:1"
