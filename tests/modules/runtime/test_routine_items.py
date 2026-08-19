"""RED proof for the typed routine work-item value Interface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    EscalationUnresolvedReason,
    RoutineAlarmEpisode,
    RoutineAlarmEpisodeState,
    RoutineAlarmKind,
    RoutineGateEvidence,
    RoutineItemSpec,
    RoutineWorkItem,
    RoutineWorkItemAlarm,
    RoutineWorkItemReceipt,
    RoutineWorkItemStatus,
    RoutineWorkItemSuppression,
)

__all__: tuple[str, ...] = ()

_DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")
_SCHEDULED = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
_DIGEST = "sha256:" + "a" * 64
_NAIVE = datetime(2026, 8, 18, 6, 0)  # noqa: DTZ001 - the refusal under proof
_MAX_TIMEOUT_SECONDS = 86400


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


def _spec(**overrides: object) -> RoutineItemSpec:
    fields: dict[str, object] = {
        "item_key": "operator-report",
        "knowledge_ref": "routine-operator-report",
        "document_id": _DOCUMENT_ID,
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
    }
    fields.update(overrides)
    return RoutineItemSpec(**fields)  # type: ignore[arg-type]


def test_routine_item_spec_refuses_every_malformed_field() -> None:
    with pytest.raises(ValueError, match="item key must be stable"):
        _spec(item_key="Operator Report")
    with pytest.raises(ValueError, match="must carry a Knowledge reference"):
        _spec(knowledge_ref="Operator Report")
    with pytest.raises(TypeError, match="Knowledge document UUID"):
        _spec(document_id="not-a-uuid")
    with pytest.raises(ValueError, match="owner seat is outside"):
        _spec(owner_seat="Commander")
    with pytest.raises(ValueError, match="escalation seat is outside"):
        _spec(escalation_seat="")


def _gate(**overrides: object) -> RoutineGateEvidence:
    fields: dict[str, object] = {
        "kind": "always",
        "watermark_kind": "none",
        "watermark_position": None,
        "observed_count": 0,
        "detail": "always gate",
    }
    fields.update(overrides)
    return RoutineGateEvidence(**fields)  # type: ignore[arg-type]


def test_gate_evidence_refuses_anything_but_a_fired_typed_result() -> None:
    with pytest.raises(ValueError, match="gate kind is outside the closed set"):
        _gate(kind="whenever")
    with pytest.raises(ValueError, match="watermark kind is outside"):
        _gate(watermark_kind="events.local_time")
    with pytest.raises(ValueError, match="only fired gate evidence"):
        _gate(result="skipped")
    with pytest.raises(ValueError, match="observed count must be non-negative"):
        _gate(observed_count=-1)
    with pytest.raises(ValueError, match="gate detail is outside"):
        _gate(detail="")
    with pytest.raises(ValueError, match="watermark must be timezone-aware"):
        _gate(watermark_position=_NAIVE)

    fired = _gate(
        kind="open_tickets_above",
        watermark_kind="tickets.nonterminal",
        watermark_position=_SCHEDULED,
        observed_count=4,
    )
    assert fired.response_payload()["watermark_position"] == _SCHEDULED.isoformat()


def _receipt(**overrides: object) -> RoutineWorkItemReceipt:
    fields: dict[str, object] = {
        "receipt_id": uuid4(),
        "work_item_id": uuid4(),
        "owner_seat": "ctower-commander",
        "artifact_ref": "artifact:operator-report/2026-08-18",
        "delivered_at": _SCHEDULED,
    }
    fields.update(overrides)
    return RoutineWorkItemReceipt(**fields)  # type: ignore[arg-type]


def test_receipt_refuses_every_malformed_delivery_fact() -> None:
    with pytest.raises(TypeError, match="receipt identities must be UUIDs"):
        _receipt(receipt_id="not-a-uuid")
    with pytest.raises(ValueError, match="receipt owner seat is invalid"):
        _receipt(owner_seat="Commander")
    with pytest.raises(ValueError, match="requires a delivered artifact reference"):
        _receipt(artifact_ref="")
    with pytest.raises(ValueError, match="receipt time must be timezone-aware"):
        _receipt(delivered_at=_NAIVE)
    with pytest.raises(TypeError, match="command_id must be a UUID"):
        _receipt(command_id="not-a-uuid")
    with pytest.raises(TypeError, match="event_id must be a UUID"):
        _receipt(event_id="not-a-uuid")

    payload = _receipt(command_id=uuid4(), event_id=uuid4()).response_payload()
    assert payload["durability_state"] == "durability_pending"


def _item(**overrides: object) -> RoutineWorkItem:
    fields: dict[str, object] = {
        "work_item_id": uuid4(),
        "tenant_id": uuid4(),
        "routine_ref": "mc-cron.operator-report@1",
        "revision_digest": "sha256:" + "a" * 64,
        "scheduled_for": _SCHEDULED,
        "window_ends_at": _SCHEDULED + timedelta(minutes=30),
        "owner_seat": "ctower-commander",
        "escalation_seat": "ctower-commander",
        "knowledge_ref": "routine-operator-report",
        "document_id": _DOCUMENT_ID,
        "gate_evidence": _gate(),
        "created_at": _SCHEDULED,
    }
    fields.update(overrides)
    return RoutineWorkItem(**fields)  # type: ignore[arg-type]


def test_work_item_refuses_malformed_identity_reference_and_window() -> None:
    with pytest.raises(TypeError, match="work-item identities must be UUIDs"):
        _item(tenant_id="not-a-uuid")
    with pytest.raises(ValueError, match="reference must be versioned"):
        _item(routine_ref="mc-cron.operator-report")
    with pytest.raises(ValueError, match="revision must be content addressed"):
        _item(revision_digest="sha256:not-a-digest")
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _item(created_at=_NAIVE)
    with pytest.raises(ValueError, match="window must end after it starts"):
        _item(window_ends_at=_SCHEDULED)


def test_work_item_refuses_malformed_seats_pointer_and_receipt_shape() -> None:
    with pytest.raises(ValueError, match="seat is outside the authored contract"):
        _item(owner_seat="Commander")
    with pytest.raises(ValueError, match="Knowledge reference is invalid"):
        _item(knowledge_ref="Operator Report")
    with pytest.raises(TypeError, match="Knowledge document must be a UUID"):
        _item(document_id="not-a-uuid")
    with pytest.raises(TypeError, match="gate evidence is required"):
        _item(gate_evidence={"kind": "always"})
    with pytest.raises(ValueError, match="open Routine work item cannot carry a receipt"):
        _item(receipt=_receipt())
    with pytest.raises(ValueError, match="closed Routine work item requires a receipt"):
        _item(status=RoutineWorkItemStatus.CLOSED)

    receipt = _receipt()
    closed = _item(status=RoutineWorkItemStatus.CLOSED, receipt=receipt)
    payload = cast(dict[str, object], closed.response_payload()["receipt"])
    assert payload["artifact_ref"] == receipt.artifact_ref


def test_completion_command_refuses_malformed_identities_and_artifact() -> None:
    with pytest.raises(TypeError, match="command identities must be UUIDs"):
        CompleteRoutineWorkItemCommand(cast(UUID, "not-a-uuid"), uuid4(), "artifact:x")
    with pytest.raises(ValueError, match="artifact reference is invalid"):
        CompleteRoutineWorkItemCommand(uuid4(), uuid4(), "x" * 513)


def test_suppression_and_alarm_render_their_recorded_windows() -> None:
    suppression = RoutineWorkItemSuppression(
        suppression_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        scheduled_for=_SCHEDULED,
        blocking_item_id=uuid4(),
        recorded_at=_SCHEDULED,
    )
    alarm = RoutineWorkItemAlarm(
        alarm_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        revision_digest=_DIGEST,
        scheduled_for=_SCHEDULED,
        work_item_id=None,
        escalation_seat="ctower-commander",
        kind=RoutineAlarmKind.MISSED_WINDOW,
        recorded_at=_SCHEDULED,
    )

    assert suppression.response_payload()["window"] == _SCHEDULED.isoformat()
    assert alarm.response_payload()["work_item_id"] is None
    assert alarm.response_payload()["kind"] == "missed_window"
    assert alarm.response_payload()["unresolved_reason"] is None


def test_the_writer_can_never_author_a_window_that_ends_before_it_starts() -> None:
    """F1 world: only the test derived an expiry from wall time; the writer cannot.

    The production path sets ``window_ends_at = scheduled_for + timeout_seconds``.
    ``timeout_seconds`` is bounded to at least one second by the Routine revision
    value type and again by the ``routine_revisions`` column check, so migration
    0079's ``window_ends_at > scheduled_for`` constraint is unreachable from it.
    """

    for refused in (0, -1, _MAX_TIMEOUT_SECONDS + 1):
        with pytest.raises(ValueError, match="Routine timeout is outside"):
            _revision_with_timeout(refused)
    for accepted in (1, 600, _MAX_TIMEOUT_SECONDS):
        revision = _revision_with_timeout(accepted)
        assert _SCHEDULED + timedelta(seconds=revision.timeout_seconds) > _SCHEDULED

    ledger = (
        Path(__file__).parents[3]
        / "packages/ctower-kernel/migrations/0019_outbox_routine_health.sql"
    ).read_text(encoding="utf-8")
    assert "timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 86400)" in ledger


def test_alarm_observation_binds_its_unresolved_reason_to_the_unresolved_kind() -> None:
    with pytest.raises(ValueError, match="unresolved escalation observation"):
        _alarm(RoutineAlarmKind.MISSED_WINDOW, EscalationUnresolvedReason.STALE)
    with pytest.raises(ValueError, match="unresolved escalation observation"):
        _alarm(RoutineAlarmKind.ESCALATION_UNRESOLVED, None)

    episode = RoutineAlarmEpisode(
        tenant_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        revision_digest=_DIGEST,
        scheduled_for=_SCHEDULED,
        observations=(
            _alarm(RoutineAlarmKind.DEGRADED_READ, None),
            _alarm(RoutineAlarmKind.MISSED_WINDOW, None),
        ),
    )
    assert episode.state is RoutineAlarmEpisodeState.CONFIRMED_UNCONSUMED
    assert episode.ordinary_alarms == 1
    assert episode.response_payload()["state"] == "confirmed-unconsumed"


def test_alarm_episode_refuses_an_empty_or_repeated_observation_set() -> None:
    with pytest.raises(ValueError, match="at least one observation"):
        _episode(())
    with pytest.raises(ValueError, match="each observation kind at most once"):
        _episode(
            (
                _alarm(RoutineAlarmKind.DEGRADED_READ, None),
                _alarm(RoutineAlarmKind.DEGRADED_READ, None),
            )
        )
    recovered = _episode(
        (
            _alarm(RoutineAlarmKind.DEGRADED_READ, None),
            _alarm(RoutineAlarmKind.RECOVERED_RECEIPTED, None),
        )
    )
    unresolved = _episode(
        (_alarm(RoutineAlarmKind.ESCALATION_UNRESOLVED, EscalationUnresolvedReason.FOREIGN_SCOPE),)
    )
    assert recovered.state is RoutineAlarmEpisodeState.RECOVERED_RECEIPTED
    assert recovered.ordinary_alarms == 0
    assert unresolved.state is RoutineAlarmEpisodeState.ESCALATION_UNRESOLVED


def _revision_with_timeout(timeout_seconds: int) -> RoutineRevision:
    return RoutineRevision(
        routine_ref="mc-cron.operator-report@1",
        revision_digest=_DIGEST,
        schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.ALWAYS_ENQUEUE_BOUNDED,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="routine_item",
        timeout_seconds=timeout_seconds,
        component_digests=("sha256:" + "b" * 64,),
        minute_marks=(0,),
        routine_item=_spec(),
    )


def _alarm(
    kind: RoutineAlarmKind, reason: EscalationUnresolvedReason | None
) -> RoutineWorkItemAlarm:
    return RoutineWorkItemAlarm(
        alarm_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        revision_digest=_DIGEST,
        scheduled_for=_SCHEDULED,
        work_item_id=uuid4(),
        escalation_seat="ctower-commander",
        kind=kind,
        recorded_at=_SCHEDULED,
        unresolved_reason=reason,
    )


def _episode(observations: tuple[RoutineWorkItemAlarm, ...]) -> RoutineAlarmEpisode:
    return RoutineAlarmEpisode(
        tenant_id=uuid4(),
        routine_ref="mc-cron.operator-report@1",
        revision_digest=_DIGEST,
        scheduled_for=_SCHEDULED,
        observations=observations,
    )
