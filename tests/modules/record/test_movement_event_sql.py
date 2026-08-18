"""Kernel mapping tests for the movement event SQL read boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ctower_kernel.record import _movement_event_sql as sql

__all__: tuple[str, ...] = ()

_EVENT_ID = UUID("00000000-0000-7000-8000-000000000001")
_TICKET_ID = UUID("00000000-0000-7000-8000-000000000002")
_OCCURRED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
_RECORD_POSITION = 12
_WORKFLOW_VERSION = 2


def test_event_row_mapper_preserves_transition_provenance() -> None:
    event = sql._event(
        {
            "event_id": _EVENT_ID,
            "record_position": _RECORD_POSITION,
            "server_time": _OCCURRED_AT,
            "payload": {
                "ticket_id": str(_TICKET_ID),
                "source_stage": "capture",
                "stage": "frame",
                "evaluation_ref": "00000000-0000-7000-8000-000000000003",
                "workflow_ref": "fixture.workflow@1",
                "workflow_version": _WORKFLOW_VERSION,
            },
        }
    )

    assert event.event_id == _EVENT_ID
    assert event.record_position == _RECORD_POSITION
    assert event.ticket_id == _TICKET_ID
    assert event.from_stage == "capture"
    assert event.to_stage == "frame"
    assert event.evaluation_ref == "00000000-0000-7000-8000-000000000003"
    assert event.workflow_ref == "fixture.workflow@1"
    assert event.workflow_version == _WORKFLOW_VERSION
    assert event.occurred_at == _OCCURRED_AT


def test_count_row_mapper_defaults_pre_enrichment_provenance_to_empty() -> None:
    row = sql._count_row(
        {
            "project_key": "ctower",
            "server_time": _OCCURRED_AT,
            "payload": {"stage": "frame"},
        }
    )

    assert row.project_key == "ctower"
    assert row.source_stage == ""
    assert row.stage == "frame"
    assert row.occurred_at == _OCCURRED_AT


def test_event_row_mapper_defaults_pre_enrichment_fields_to_empty() -> None:
    event = sql._event(
        {
            "event_id": _EVENT_ID,
            "record_position": _RECORD_POSITION,
            "server_time": _OCCURRED_AT,
            "payload": {"ticket_id": str(_TICKET_ID), "stage": "frame"},
        }
    )

    assert event.from_stage == ""
    assert event.evaluation_ref == ""
    assert event.workflow_ref == ""
    assert event.workflow_version == 0
