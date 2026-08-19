"""AC-RWI-05: append-only alarm episodes over the stable Routine window identity.

One episode is every typed observation sharing ``(tenant_id, revision_digest,
scheduled_for)``. The episode state is derived from the observations, never
stored, so a partial read can never present itself as a clean no-alarm and a
later authoritative read resolves the same episode instead of opening a new one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from itertools import groupby
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.routine_work_item_events import RoutineWorkItemAlarmRaisedPayload
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.runtime._routine_ids import stable_uuid7 as _stable_uuid7
from ctower_kernel.runtime.items import (
    EscalationUnresolvedReason,
    RoutineAlarmEpisode,
    RoutineAlarmKind,
    RoutineWorkItemAlarm,
)

__all__: tuple[str, ...] = ()

_TERMINAL_KINDS = ("missed_window", "recovered_receipted")
_GATE_EVIDENCE_FIELDS = frozenset(
    {"detail", "kind", "observed_count", "result", "watermark_kind", "watermark_position"}
)


def append_episode_observations(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    now: datetime,
) -> list[RoutineWorkItemAlarm]:
    """Advance every open episode once, in one already-locked scan transaction."""

    appended = _observe_open_items(connection, tenant_id, actor_principal_id, now)
    appended.extend(_resolve_receipted_episodes(connection, tenant_id, actor_principal_id, now))
    return appended


def alarm_episodes(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> tuple[RoutineAlarmEpisode, ...]:
    """Project every episode for one tenant from its append-only observations."""

    rows = connection.execute(
        """
        SELECT alarm_id, routine_ref, revision_digest, scheduled_for, work_item_id,
            escalation_seat, kind, unresolved_reason, recorded_at
        FROM routine_work_item_alarms
        WHERE tenant_id = %s
        ORDER BY revision_digest, scheduled_for, recorded_at, alarm_id
        """,
        (tenant_id,),
    ).fetchall()
    episodes: list[RoutineAlarmEpisode] = []
    for key, group in groupby(rows, key=lambda row: (row["revision_digest"], row["scheduled_for"])):
        observations = tuple(_alarm(row) for row in group)
        episodes.append(
            RoutineAlarmEpisode(
                tenant_id=tenant_id,
                routine_ref=observations[0].routine_ref,
                revision_digest=_hex(cast(bytes, key[0])),
                scheduled_for=cast(datetime, key[1]),
                observations=observations,
            )
        )
    return tuple(episodes)


def _observe_open_items(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    now: datetime,
) -> list[RoutineWorkItemAlarm]:
    rows = connection.execute(
        """
        SELECT work_item_id, routine_ref, revision_digest, scheduled_for, window_ends_at,
            owner_seat, escalation_seat, gate_evidence
        FROM inbox_work_items
        WHERE tenant_id = %s AND status = 'open'
        ORDER BY window_ends_at, work_item_id
        FOR UPDATE
        """,
        (tenant_id,),
    ).fetchall()
    appended: list[RoutineWorkItemAlarm] = []
    for row in rows:
        observation = _open_item_observation(connection, tenant_id, row, now)
        if observation is None:
            continue
        kind, seat, reason = observation
        alarm = _append_observation(
            connection, tenant_id, actor_principal_id, row, kind, seat, reason, now
        )
        if alarm is not None:
            appended.append(alarm)
    return appended


def _open_item_observation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    row: dict[str, object],
    now: datetime,
) -> tuple[RoutineAlarmKind, str, EscalationUnresolvedReason | None] | None:
    """Decide the one observation this open item contributes to its episode."""

    if not _valid_gate_evidence(row["gate_evidence"]):
        return (RoutineAlarmKind.DEGRADED_READ, str(row["escalation_seat"]), None)
    if cast(datetime, row["window_ends_at"]) > now:
        return None
    seat, reason = _resolve_escalation(connection, tenant_id, row)
    if reason is not None:
        return (RoutineAlarmKind.ESCALATION_UNRESOLVED, seat, reason)
    return (RoutineAlarmKind.MISSED_WINDOW, seat, None)


def _resolve_receipted_episodes(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    now: datetime,
) -> list[RoutineWorkItemAlarm]:
    """Resolve an open episode whose item has since been closed by a receipt."""

    rows = connection.execute(
        """
        SELECT item.work_item_id, item.routine_ref, item.revision_digest, item.scheduled_for,
            item.escalation_seat
        FROM inbox_work_items AS item
        WHERE item.tenant_id = %s AND item.status = 'closed'
          AND EXISTS (
              SELECT 1 FROM routine_work_item_alarms AS opened
              WHERE opened.tenant_id = item.tenant_id
                AND opened.revision_digest = item.revision_digest
                AND opened.scheduled_for = item.scheduled_for
          )
          AND NOT EXISTS (
              SELECT 1 FROM routine_work_item_alarms AS closed
              WHERE closed.tenant_id = item.tenant_id
                AND closed.revision_digest = item.revision_digest
                AND closed.scheduled_for = item.scheduled_for
                AND closed.kind = ANY(%s)
          )
        ORDER BY item.scheduled_for, item.work_item_id
        FOR UPDATE
        """,
        (tenant_id, list(_TERMINAL_KINDS)),
    ).fetchall()
    appended: list[RoutineWorkItemAlarm] = []
    for row in rows:
        alarm = _append_observation(
            connection,
            tenant_id,
            actor_principal_id,
            row,
            RoutineAlarmKind.RECOVERED_RECEIPTED,
            str(row["escalation_seat"]),
            None,
            now,
        )
        if alarm is not None:
            appended.append(alarm)
    return appended


def _resolve_escalation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    row: dict[str, object],
) -> tuple[str, EscalationUnresolvedReason | None]:
    """Resolve the active revision's binding to one live seat in the owner's scope."""

    active = connection.execute(
        """
        SELECT spec.escalation_seat
        FROM routine_triggers AS trigger
        JOIN routine_revisions AS revision
          ON revision.revision_digest = trigger.revision_digest
        JOIN routine_item_specs AS spec ON spec.revision_digest = revision.revision_digest
        WHERE trigger.tenant_id = %s AND revision.routine_ref = %s
        """,
        (tenant_id, row["routine_ref"]),
    ).fetchone()
    if active is None:
        return str(row["escalation_seat"]), EscalationUnresolvedReason.STALE
    seat = str(active["escalation_seat"])
    bindings = _seat_bindings(connection, tenant_id, seat)
    if not bindings:
        return seat, EscalationUnresolvedReason.MISSING
    owner_scope = _owner_scope(connection, tenant_id, str(row["owner_seat"]))
    in_scope = [
        binding
        for binding in bindings
        if owner_scope is None or binding["project_key"] == owner_scope
    ]
    if not in_scope:
        return seat, EscalationUnresolvedReason.FOREIGN_SCOPE
    if not any(binding["addressable"] for binding in in_scope):
        return seat, EscalationUnresolvedReason.REVOKED
    return seat, None


def _seat_bindings(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, seat_key: str
) -> list[dict[str, object]]:
    return connection.execute(
        """
        SELECT seat.project_key,
            (NOT principal.disabled AND EXISTS (
                SELECT 1 FROM principal_credentials AS credential
                WHERE credential.principal_id = seat.principal_id
                  AND credential.tenant_id = seat.tenant_id
                  AND credential.revoked_at IS NULL
            )) AS addressable
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.principal_id = seat.principal_id
         AND principal.tenant_id = seat.tenant_id
        WHERE seat.tenant_id = %s AND seat.seat_key = %s
        ORDER BY seat.project_key
        """,
        (tenant_id, seat_key),
    ).fetchall()


def _owner_scope(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, owner_seat: str
) -> str | None:
    row = connection.execute(
        """
        SELECT project_key FROM project_seats
        WHERE tenant_id = %s AND seat_key = %s
        ORDER BY project_key
        LIMIT 1
        """,
        (tenant_id, owner_seat),
    ).fetchone()
    return None if row is None else str(row["project_key"])


def _append_observation(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    actor_principal_id: UUID,
    row: dict[str, object],
    kind: RoutineAlarmKind,
    escalation_seat: str,
    reason: EscalationUnresolvedReason | None,
    now: datetime,
) -> RoutineWorkItemAlarm | None:
    work_item_id = cast(UUID, row["work_item_id"])
    revision_digest = _hex(cast(bytes, row["revision_digest"]))
    alarm_id, command_id, event_id, outbox_id = _alarm_ids(
        tenant_id, work_item_id, cast(datetime, row["scheduled_for"]), kind
    )
    alarm = RoutineWorkItemAlarm(
        alarm_id=alarm_id,
        routine_ref=str(row["routine_ref"]),
        revision_digest=revision_digest,
        scheduled_for=cast(datetime, row["scheduled_for"]),
        work_item_id=work_item_id,
        escalation_seat=escalation_seat,
        kind=kind,
        recorded_at=now,
        unresolved_reason=reason,
    )
    request_payload = alarm.response_payload()
    request_digest = hashlib.sha256(_canonical_bytes(request_payload)).digest()
    transaction = RecordTransaction(connection)
    if transaction.reserve(actor_principal_id, command_id, request_digest) is not None:
        return None
    transaction.commit_control(
        _alarm_event(tenant_id, actor_principal_id, alarm, command_id, event_id, request_digest),
        outbox_id=outbox_id,
        response_body=request_payload,
        status_code=202,
        now=now,
        topic="runtime.routine-work-item-alarms",
    )
    _insert_alarm(connection, tenant_id, alarm, event_id)
    return alarm


def _alarm_ids(
    tenant_id: UUID, work_item_id: UUID, scheduled_for: datetime, kind: RoutineAlarmKind
) -> tuple[UUID, UUID, UUID, UUID]:
    alarm_id = _stable_uuid7(
        scheduled_for,
        b"routine-work-item-alarm",
        tenant_id.bytes,
        work_item_id.bytes,
        kind.value.encode("ascii"),
    )
    identity = (tenant_id.bytes, alarm_id.bytes)
    return (
        alarm_id,
        _stable_uuid7(scheduled_for, b"routine-work-item-alarm-command", *identity),
        _stable_uuid7(scheduled_for, b"routine-work-item-alarm-event", *identity),
        _stable_uuid7(scheduled_for, b"routine-work-item-alarm-outbox", *identity),
    )


def _alarm_event(
    tenant_id: UUID,
    actor_principal_id: UUID,
    alarm: RoutineWorkItemAlarm,
    command_id: UUID,
    event_id: UUID,
    request_digest: bytes,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor_principal_id,
        aggregate_id=alarm.alarm_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.ROUTINE_WORK_ITEM_ALARM_RAISED,
        origin=EventOrigin.CONTROL_WORKER,
        payload=RoutineWorkItemAlarmRaisedPayload(
            alarm_id=alarm.alarm_id,
            routine_ref=alarm.routine_ref,
            revision_digest=alarm.revision_digest,
            scheduled_for=alarm.scheduled_for,
            work_item_id=alarm.work_item_id,
            escalation_seat=alarm.escalation_seat,
            kind=alarm.kind.value,
            recorded_at=alarm.recorded_at,
            unresolved_reason=(
                alarm.unresolved_reason.value if alarm.unresolved_reason is not None else None
            ),
        ),
        prev_hash=bytes(32),
        request_sha256=request_digest,
        sequence=1,
        server_time=alarm.recorded_at,
        stream_id=f"routine-work-item:{alarm.alarm_id}",
        tenant_id=tenant_id,
    )


def _insert_alarm(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    alarm: RoutineWorkItemAlarm,
    event_id: UUID,
) -> None:
    connection.execute(
        """
        INSERT INTO routine_work_item_alarms (
            alarm_id, tenant_id, revision_digest, routine_ref, scheduled_for, work_item_id,
            escalation_seat, kind, unresolved_reason, recorded_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            alarm.alarm_id,
            tenant_id,
            bytes.fromhex(alarm.revision_digest.removeprefix("sha256:")),
            alarm.routine_ref,
            alarm.scheduled_for,
            alarm.work_item_id,
            alarm.escalation_seat,
            alarm.kind.value,
            None if alarm.unresolved_reason is None else alarm.unresolved_reason.value,
            alarm.recorded_at,
            event_id,
        ),
    )


def _alarm(row: dict[str, object]) -> RoutineWorkItemAlarm:
    reason = row["unresolved_reason"]
    return RoutineWorkItemAlarm(
        alarm_id=cast(UUID, row["alarm_id"]),
        routine_ref=str(row["routine_ref"]),
        revision_digest=_hex(cast(bytes, row["revision_digest"])),
        scheduled_for=cast(datetime, row["scheduled_for"]),
        work_item_id=cast(UUID | None, row["work_item_id"]),
        escalation_seat=str(row["escalation_seat"]),
        kind=RoutineAlarmKind(str(row["kind"])),
        recorded_at=cast(datetime, row["recorded_at"]),
        unresolved_reason=None if reason is None else EscalationUnresolvedReason(str(reason)),
    )


def _valid_gate_evidence(value: object) -> bool:
    return isinstance(value, dict) and set(value) == _GATE_EVIDENCE_FIELDS


def _hex(value: bytes) -> str:
    return f"sha256:{value.hex()}"


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def read_alarm_episodes(dsn: str, tenant_id: UUID) -> tuple[RoutineAlarmEpisode, ...]:
    """Read the projected episodes for one tenant outside a scan transaction."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        return alarm_episodes(connection, tenant_id)
