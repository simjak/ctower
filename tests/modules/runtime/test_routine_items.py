"""RED proof for the typed routine work-item value Interface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    RoutineGateEvidence,
    RoutineItemSpec,
    RoutineWorkItem,
)


def test_routine_item_spec_has_a_knowledge_pointer_and_no_embedded_instructions() -> None:
    spec = RoutineItemSpec(
        item_key="operator-report",
        knowledge_ref="routine-operator-report",
        document_id=UUID("00000000-0000-4000-8000-000000000001"),
        owner_seat="ctower-commander",
        escalation_seat="ctower-commander",
    )
    assert spec.canonical_payload() == {
        "escalation_seat": "ctower-commander",
        "item_key": "operator-report",
        "knowledge_ref": "routine-operator-report",
        "document_id": "00000000-0000-4000-8000-000000000001",
        "owner_seat": "ctower-commander",
    }
    with pytest.raises((TypeError, ValueError), match="instruction"):
        RoutineItemSpec(
            item_key="operator-report",
            knowledge_ref="routine-operator-report",
            owner_seat="ctower-commander",
            escalation_seat="ctower-commander",
            instructions="do the report",  # type: ignore[call-arg]
        )


def test_work_item_carries_gate_window_pointer_and_completion_command() -> None:
    item_id = uuid4()
    scheduled_for = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    item = RoutineWorkItem(
        work_item_id=item_id,
        tenant_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        revision_digest="sha256:" + "a" * 64,
        scheduled_for=scheduled_for,
        window_ends_at=scheduled_for + timedelta(minutes=30),
        owner_seat="ctower-commander",
        escalation_seat="ctower-commander",
        knowledge_ref="routine-operator-report",
        document_id=UUID("00000000-0000-4000-8000-000000000001"),
        gate_evidence=RoutineGateEvidence(
            kind="always",
            watermark_kind="none",
            watermark_position=None,
            observed_count=0,
            detail="always gate",
        ),
        created_at=scheduled_for,
    )
    payload = item.response_payload()
    assert payload["work_item_id"] == str(item_id)
    assert payload["knowledge_ref"] == "routine-operator-report"
    assert payload["document_id"] == "00000000-0000-4000-8000-000000000001"
    assert payload["window"] == {
        "scheduled_for": scheduled_for.isoformat(),
        "ends_at": (scheduled_for + timedelta(minutes=30)).isoformat(),
    }
    assert "prompt" not in payload and "instructions" not in payload and "body" not in payload

    command = CompleteRoutineWorkItemCommand(
        uuid4(), item_id, "artifact:operator-report/2026-08-15"
    )
    assert command.request_payload() == {
        "artifact_ref": "artifact:operator-report/2026-08-15",
        "work_item_id": str(item_id),
    }
