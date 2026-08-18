"""Refusal proofs for the strict Routine work-item Record payloads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.routine_work_item_events import (
    RoutineWorkItemAlarmRaisedPayload,
    RoutineWorkItemAppendedPayload,
    RoutineWorkItemCompletedPayload,
    RoutineWorkItemSuppressedPayload,
    validate_routine_work_item_identity,
)

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + "a" * 64
_SCHEDULED = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
_ENDS = _SCHEDULED + timedelta(minutes=30)
_NAIVE = datetime(2026, 8, 18, 6, 0)  # noqa: DTZ001 - the refusal under proof


def _evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "kind": "always",
        "result": "fired",
        "watermark_kind": "none",
        "watermark_position": None,
        "observed_count": 0,
        "detail": "always gate",
    }
    evidence.update(overrides)
    return evidence


def _appended(**overrides: object) -> RoutineWorkItemAppendedPayload:
    fields: dict[str, object] = {
        "work_item_id": uuid4(),
        "routine_ref": "mc-cron.operator-report@1",
        "revision_digest": _DIGEST,
        "scheduled_for": _SCHEDULED,
        "window_ends_at": _ENDS,
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
        "knowledge_ref": "routine-operator-report",
        "document_id": uuid4(),
        "gate_evidence": _evidence(),
    }
    fields.update(overrides)
    return RoutineWorkItemAppendedPayload(**fields)  # type: ignore[arg-type]


def test_appended_payload_refuses_every_malformed_identity_and_window() -> None:
    with pytest.raises(ValueError, match="reference is invalid"):
        _appended(routine_ref="mc-cron.operator-report")
    with pytest.raises(ValueError, match="revision is invalid"):
        _appended(revision_digest="sha256:not-a-digest")
    with pytest.raises(ValueError, match="seat is invalid"):
        _appended(owner_seat="Commander")
    with pytest.raises(ValueError, match="seat is invalid"):
        _appended(escalation_seat="")
    with pytest.raises(TypeError, match="work_item_id must be a UUID"):
        _appended(work_item_id="not-a-uuid")
    with pytest.raises(ValueError, match="scheduled_for must be timezone-aware"):
        _appended(scheduled_for=_NAIVE)
    with pytest.raises(ValueError, match="window must end after it starts"):
        _appended(window_ends_at=_SCHEDULED)
    with pytest.raises(ValueError, match="Knowledge reference is invalid"):
        _appended(knowledge_ref="Operator Report")
    with pytest.raises(TypeError, match="document_id must be a UUID"):
        _appended(document_id="not-a-uuid")


def test_appended_payload_refuses_every_malformed_gate_evidence() -> None:
    with pytest.raises(TypeError, match="gate evidence must be an object"):
        _appended(gate_evidence="always")
    with pytest.raises(ValueError, match="unknown or missing fields"):
        _appended(gate_evidence={"kind": "always"})
    with pytest.raises(ValueError, match="kind is outside the closed set"):
        _appended(gate_evidence=_evidence(kind="whenever"))
    with pytest.raises(ValueError, match="must describe a fired gate"):
        _appended(gate_evidence=_evidence(result="skipped"))
    with pytest.raises(ValueError, match="watermark is invalid"):
        _appended(gate_evidence=_evidence(watermark_kind="events.local_time"))
    with pytest.raises(ValueError, match="must be an ISO timestamp"):
        _appended(gate_evidence=_evidence(watermark_position="yesterday"))
    with pytest.raises(ValueError, match="watermark_position must be timezone-aware"):
        _appended(gate_evidence=_evidence(watermark_position=_NAIVE))
    with pytest.raises(ValueError, match="observed count is invalid"):
        _appended(gate_evidence=_evidence(observed_count=-1))
    with pytest.raises(ValueError, match="detail is invalid"):
        _appended(gate_evidence=_evidence(detail=""))


def test_appended_mapping_renders_a_datetime_watermark_as_an_iso_string() -> None:
    payload = _appended(
        gate_evidence=_evidence(
            kind="new_movement_since_watermark",
            watermark_kind="events.server_time",
            watermark_position=_SCHEDULED,
            observed_count=3,
        )
    )

    mapping = cast(dict[str, object], payload.to_mapping()["gate_evidence"])

    assert mapping["watermark_position"] == _SCHEDULED.isoformat()
    assert payload.to_mapping()["scheduled_for"] == _SCHEDULED.isoformat()


def test_suppression_and_completion_payloads_refuse_malformed_facts() -> None:
    with pytest.raises(TypeError, match="suppression_id must be a UUID"):
        RoutineWorkItemSuppressedPayload(
            suppression_id=cast(UUID, "not-a-uuid"),
            routine_ref="mc-cron.operator-report@1",
            scheduled_for=_SCHEDULED,
            blocking_item_id=uuid4(),
        )
    with pytest.raises(ValueError, match="suppression reference is invalid"):
        RoutineWorkItemSuppressedPayload(
            suppression_id=uuid4(),
            routine_ref="mc-cron.operator-report",
            scheduled_for=_SCHEDULED,
            blocking_item_id=uuid4(),
        )
    with pytest.raises(ValueError, match="completion owner seat is invalid"):
        _completed(owner_seat="Commander")
    with pytest.raises(ValueError, match="completion artifact reference is invalid"):
        _completed(artifact_ref="")
    with pytest.raises(ValueError, match="delivered_at must be timezone-aware"):
        _completed(delivered_at=_NAIVE)


def _completed(**overrides: object) -> RoutineWorkItemCompletedPayload:
    fields: dict[str, object] = {
        "work_item_id": uuid4(),
        "receipt_id": uuid4(),
        "owner_seat": "ctower-commander",
        "artifact_ref": "artifact:operator-report/2026-08-18",
        "delivered_at": _SCHEDULED,
    }
    fields.update(overrides)
    return RoutineWorkItemCompletedPayload(**fields)  # type: ignore[arg-type]


def _alarm(**overrides: object) -> RoutineWorkItemAlarmRaisedPayload:
    fields: dict[str, object] = {
        "alarm_id": uuid4(),
        "routine_ref": "mc-cron.operator-report@1",
        "scheduled_for": _SCHEDULED,
        "work_item_id": uuid4(),
        "escalation_seat": "ctower-commander",
        "kind": "missed_window",
        "recorded_at": _ENDS,
    }
    fields.update(overrides)
    return RoutineWorkItemAlarmRaisedPayload(**fields)  # type: ignore[arg-type]


def test_alarm_payload_refuses_malformed_facts_and_allows_an_unbound_window() -> None:
    with pytest.raises(TypeError, match="alarm_id must be a UUID"):
        _alarm(alarm_id="not-a-uuid")
    with pytest.raises(TypeError, match="work_item_id must be a UUID"):
        _alarm(work_item_id="not-a-uuid")
    with pytest.raises(ValueError, match="alarm reference is invalid"):
        _alarm(routine_ref="mc-cron.operator-report")
    with pytest.raises(ValueError, match="alarm escalation seat is invalid"):
        _alarm(escalation_seat="Commander")
    with pytest.raises(ValueError, match="alarm kind is outside"):
        _alarm(kind="late")
    with pytest.raises(ValueError, match="recorded_at must be timezone-aware"):
        _alarm(recorded_at=_NAIVE)

    assert _alarm(work_item_id=None).to_mapping()["work_item_id"] is None


def test_work_item_identity_binds_each_payload_to_its_own_aggregate() -> None:
    appended = _appended()
    completed = _completed()
    alarm = _alarm()
    suppression = RoutineWorkItemSuppressedPayload(
        suppression_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        scheduled_for=_SCHEDULED,
        blocking_item_id=uuid4(),
    )

    validate_routine_work_item_identity(appended.work_item_id, appended)
    validate_routine_work_item_identity(suppression.suppression_id, suppression)
    validate_routine_work_item_identity(completed.work_item_id, completed)
    validate_routine_work_item_identity(alarm.alarm_id, alarm)
    validate_routine_work_item_identity(uuid4(), object())

    with pytest.raises(ValueError, match="work-item aggregate and item identity"):
        validate_routine_work_item_identity(uuid4(), appended)
    with pytest.raises(ValueError, match="suppression aggregate and identity"):
        validate_routine_work_item_identity(uuid4(), suppression)
    with pytest.raises(ValueError, match="completion aggregate and item identity"):
        validate_routine_work_item_identity(uuid4(), completed)
    with pytest.raises(ValueError, match="alarm aggregate and identity"):
        validate_routine_work_item_identity(uuid4(), alarm)
