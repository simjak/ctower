"""AC-RTN-01..04: activity-gated Routines end-to-end over real PostgreSQL."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_kernel.runtime import Routine, RoutineRevision
from ctower_kernel.runtime.gates import ActivityGate
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
_FIVE = (
    "manibo-report",
    "structural-report",
    "manibo-merge-watch",
    "worktree-janitor-apply",
    "capacity-sentinel",
)
_EXPECTED_MIGRATED_COUNT = 5
_MAX_MINUTE_ELAPSED_SECONDS = 55.0
_TABLE_COUNT_QUERIES: dict[str, LiteralString] = {
    "routine_activity_gates": "SELECT count(*) FROM routine_activity_gates",
    "routine_gate_evaluations": "SELECT count(*) FROM routine_gate_evaluations",
    "routine_occurrences": "SELECT count(*) FROM routine_occurrences",
    "routine_revisions": "SELECT count(*) FROM routine_revisions",
    "runtime_beat_dispatch_effects": "SELECT count(*) FROM runtime_beat_dispatch_effects",
}


def _gated() -> dict[str, RoutineRevision]:
    return {
        revision.routine_ref.removeprefix("mc-cron.").removesuffix("@1"): revision
        for revision in load_routine_revisions(ROOT / "packs")
        if revision.routine_ref.startswith("mc-cron.")
    }


def test_ac_rtn_01_registration_record_is_append_only_and_owned(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    gated = _gated()
    assert set(gated) == set(_FIVE)
    report = gated["manibo-report"]
    assert report.activity_gate is not None
    assert report.activity_gate.kind == "always"

    now = datetime.now(UTC)
    for revision in gated.values():
        runtime.register(tenant.tenant_id, revision, first_fire_at=_due_mark(revision, now))

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT revision.routine_ref, gate.gate_kind, gate.gate_source,
                   gate.gate_threshold, gate.gate_project_key
            FROM routine_revisions AS revision
            JOIN routine_activity_gates AS gate
              ON gate.revision_digest = revision.revision_digest
            WHERE revision.routine_ref LIKE %s
            ORDER BY revision.routine_ref
            """,
            ("mc-cron.%",),
        ).fetchall()
    assert len(rows) == _EXPECTED_MIGRATED_COUNT
    by_ref = {row[0]: row[1:] for row in rows}
    assert by_ref["mc-cron.capacity-sentinel@1"] == ("open_tickets_above", None, 0, None)
    assert by_ref["mc-cron.manibo-merge-watch@1"][0] == "new_movement_since_watermark"

    # registration is idempotent: replaying register appends nothing
    counts = _table_counts(tenant, "routine_activity_gates")
    for revision in gated.values():
        runtime.register(tenant.tenant_id, revision)
    assert _table_counts(tenant, "routine_activity_gates") == counts

    # unknown gate / foreign scope / unowned registration refuse with zero mutation
    with pytest.raises((ValueError, TypeError)):
        ActivityGate(kind="sql_expression")
    before = _table_counts(tenant, "routine_revisions")
    bogus = _replace_ref(report, "mc-cron.not-in-pack@1")
    with pytest.raises(ValueError, match="digest conflicts"):
        runtime.register(tenant.tenant_id, bogus)
    assert _table_counts(tenant, "routine_revisions") == before


def test_ac_rtn_02_gate_true_fires_one_dispatch_fact_with_evidence(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    gated = _gated()
    sentinel = gated["capacity-sentinel"]

    _create_open_ticket(tenant)
    now = datetime.now(UTC)
    runtime.register(tenant.tenant_id, sentinel, first_fire_at=_due_mark(sentinel, now))
    scan = runtime.scan(tenant.tenant_id)

    fires = [
        o
        for o in scan.occurrences
        if o.routine_ref == sentinel.routine_ref and o.outcome.value == "queued"
    ]
    assert len(fires) == 1, "open ticket + due schedule must fire exactly once"
    assert not [e for e in scan.beat_dispatches if e.routine_ref != sentinel.routine_ref]

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT eval.result, eval.watermark_kind, eval.watermark_position, eval.observed_count
            FROM routine_gate_evaluations AS eval
            JOIN routine_revisions AS revision ON revision.revision_digest = eval.revision_digest
            WHERE revision.routine_ref = %s
            ORDER BY eval.evaluated_at
            """,
            (sentinel.routine_ref,),
        ).fetchone()
    assert row is not None and row[0] == "fired"
    assert row[1] == "tickets.nonterminal"
    assert cast(int, row[3]) >= 1
    assert row[2] is not None


def test_ac_rtn_02_gate_false_appends_typed_skip_fact_never_silence(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    sentinel = _gated()["capacity-sentinel"]

    # NO ticket rows: gate answers false
    now = datetime.now(UTC)
    runtime.register(tenant.tenant_id, sentinel, first_fire_at=_due_mark(sentinel, now))
    scan = runtime.scan(tenant.tenant_id)

    skips = [
        o
        for o in scan.occurrences
        if o.routine_ref == sentinel.routine_ref and o.outcome.value == "skipped"
    ]
    assert len(skips) == 1, "false gate must append a visible skipped occurrence"
    assert scan.beat_dispatches == (), "false gate must emit no dispatch effect"

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT eval.result, eval.observed_count, eval.detail
            FROM routine_gate_evaluations AS eval
            JOIN routine_revisions AS revision ON revision.revision_digest = eval.revision_digest
            WHERE revision.routine_ref = %s
            """,
            (sentinel.routine_ref,),
        ).fetchone()
    assert row is not None and row[0] == "skipped"
    assert cast(int, row[1]) == 0
    assert row[2] and "0 nonterminal" in cast(str, row[2])


def test_ac_rtn_02_project_scoped_gate_ignores_foreign_ticket(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    sentinel = _gated()["capacity-sentinel"]

    # The fixture ticket belongs to ctower; this gate is explicitly scoped to
    # manibo and must not fire from a foreign project's nonterminal work.
    _create_open_ticket(tenant)

    project_sentinel = replace(
        sentinel,
        routine_ref="mc-cron.capacity-sentinel-project@1",
        revision_digest="sha256:" + "ef" * 32,
        activity_gate=ActivityGate(kind="open_tickets_above", threshold=0, project_key="manibo"),
    )
    now = datetime.now(UTC)
    runtime.register(
        tenant.tenant_id, project_sentinel, first_fire_at=_due_mark(project_sentinel, now)
    )
    scan = runtime.scan(tenant.tenant_id)

    occurrences = [
        occurrence
        for occurrence in scan.occurrences
        if occurrence.routine_ref == project_sentinel.routine_ref
    ]
    assert [occurrence.outcome.value for occurrence in occurrences] == ["skipped"]
    assert scan.beat_dispatches == ()

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT result, observed_count, detail
            FROM routine_gate_evaluations AS evaluation
            JOIN routine_revisions AS revision
              ON revision.revision_digest = evaluation.revision_digest
            WHERE revision.routine_ref = %s
            """,
            (project_sentinel.routine_ref,),
        ).fetchone()
    assert row is not None and row[0] == "skipped"
    assert cast(int, row[1]) == 0
    assert row[2] and "0 nonterminal" in cast(str, row[2])


def test_ac_rtn_02_movement_gate_skips_when_quiet_and_fires_on_movement(
    tenant: TenantFixture,
) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    watcher = _gated()["manibo-merge-watch"]

    _await_mark_gap()
    now = datetime.now(UTC)
    mark_now = _due_mark(watcher, now)
    runtime.register(tenant.tenant_id, watcher, first_fire_at=mark_now)
    # baseline evaluation: establishes watermark, fires (first evaluation passes)
    first = runtime.scan(tenant.tenant_id)
    assert [o.outcome.value for o in first.occurrences if o.routine_ref == watcher.routine_ref] == [
        "queued"
    ]
    assert [e.routine_ref for e in first.beat_dispatches] == [watcher.routine_ref]

    # quiet interval at a later due instant: no new events -> typed skip fact, no effect
    quiet_due = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=2)
    _advance_trigger(tenant, watcher, quiet_due)
    second = runtime.scan(tenant.tenant_id)
    quiet = [o for o in second.occurrences if o.routine_ref == watcher.routine_ref]
    assert [o.outcome.value for o in quiet] == ["skipped"]
    assert second.beat_dispatches == ()

    # movement: a new event lands -> next evaluation fires
    _append_event(tenant)
    third_due = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
    assert third_due > quiet_due
    _advance_trigger(tenant, watcher, third_due)
    third = runtime.scan(tenant.tenant_id)
    moved = [o for o in third.occurrences if o.routine_ref == watcher.routine_ref]
    assert [o.outcome.value for o in moved] == ["queued"]
    effects = [e for e in third.beat_dispatches if e.routine_ref == watcher.routine_ref]
    assert len(effects) == 1


def test_ac_rtn_02_exact_replay_of_an_evaluation_appends_nothing(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    sentinel = _gated()["capacity-sentinel"]

    _create_open_ticket(tenant)
    now = datetime.now(UTC)
    due = _due_mark(sentinel, now)
    runtime.register(tenant.tenant_id, sentinel, first_fire_at=due)
    runtime.scan(tenant.tenant_id)

    baseline = _table_counts(
        tenant, "routine_gate_evaluations", "routine_occurrences", "runtime_beat_dispatch_effects"
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        watermark_before = connection.execute(
            """
            SELECT watermark_position, updated_at
            FROM routine_gate_watermarks AS watermark
            JOIN routine_revisions AS revision
              ON revision.revision_digest = watermark.revision_digest
            WHERE watermark.tenant_id = %s AND revision.routine_ref = %s
            """,
            (tenant.tenant_id, sentinel.routine_ref),
        ).fetchone()
    # exact replay: trigger reset to the same due instant, scan again
    _advance_trigger(tenant, sentinel, due)
    replay = runtime.scan(tenant.tenant_id)
    assert replay.occurrences == ()
    assert replay.beat_dispatches == ()
    assert (
        _table_counts(
            tenant,
            "routine_gate_evaluations",
            "routine_occurrences",
            "runtime_beat_dispatch_effects",
        )
        == baseline
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        watermark_after = connection.execute(
            """
            SELECT watermark_position, updated_at
            FROM routine_gate_watermarks AS watermark
            JOIN routine_revisions AS revision
              ON revision.revision_digest = watermark.revision_digest
            WHERE watermark.tenant_id = %s AND revision.routine_ref = %s
            """,
            (tenant.tenant_id, sentinel.routine_ref),
        ).fetchone()
    assert watermark_after == watermark_before, (
        "exact evaluation replay must not mutate its watermark"
    )


def test_ac_rtn_02_degraded_read_yields_typed_degraded_fact_not_clean_fire(
    tenant: TenantFixture,
) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    watcher = _gated()["manibo-merge-watch"]

    _await_mark_gap()
    now = datetime.now(UTC)
    mark_now = _due_mark(watcher, now)
    runtime.register(tenant.tenant_id, watcher, first_fire_at=mark_now)
    runtime.scan(tenant.tenant_id)  # baseline fires and establishes the watermark

    degraded_due = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=2)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute("REVOKE SELECT ON events FROM ctower_svc")
        connection.commit()
    try:
        _advance_trigger(tenant, watcher, degraded_due)
        degraded = runtime.scan(tenant.tenant_id)
        occurrences = [o for o in degraded.occurrences if o.routine_ref == watcher.routine_ref]
        assert [o.outcome.value for o in occurrences] == ["skipped"]
        assert degraded.beat_dispatches == ()
    finally:
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            connection.execute("GRANT SELECT ON events TO ctower_svc")
            connection.commit()

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT eval.result, eval.detail FROM routine_gate_evaluations AS eval
            JOIN routine_revisions AS revision ON revision.revision_digest = eval.revision_digest
            WHERE revision.routine_ref = %s ORDER BY eval.evaluated_at DESC
            """,
            (watcher.routine_ref,),
        ).fetchone()
    assert row is not None and row[0] == "degraded"
    assert row[1] and "degraded" in cast(str, row[1]).lower()


def test_ac_rtn_03_five_representative_schedules_register_and_fire(tenant: TenantFixture) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    gated = _gated()
    _create_open_ticket(tenant)  # sentinel gate true
    _append_event(tenant)

    now = datetime.now(UTC)
    for revision in gated.values():
        runtime.register(tenant.tenant_id, revision, first_fire_at=_due_mark(revision, now))
    scan = runtime.scan(tenant.tenant_id)

    fired_refs = {o.routine_ref for o in scan.occurrences if o.outcome.value == "queued"}
    assert fired_refs == {revision.routine_ref for revision in gated.values()}
    assert len(scan.beat_dispatches) == _EXPECTED_MIGRATED_COUNT
    for effect in scan.beat_dispatches:
        assert effect.routine_ref.startswith("mc-cron.")
        assert effect.spec.target_session in ("commander", "mc-commander-manibo")

    # Ctower owns only the queued occurrence evidence. Host-twin activity and
    # crontab deletion remain external-custodian facts.


def _due_mark(revision: RoutineRevision, now: datetime) -> datetime:
    due = now.replace(second=0, microsecond=0)
    while due.minute not in revision.minute_marks:
        due -= timedelta(minutes=1)
    return due


def _previous_due(revision: RoutineRevision, due: datetime) -> datetime:
    previous = due - timedelta(minutes=1)
    while previous.minute not in revision.minute_marks:
        previous -= timedelta(minutes=1)
    return previous


def _await_mark_gap(minimum_seconds: float = 5.0) -> None:
    """Sleep past a fresh mark so intra-minute due instants stay unique."""

    while True:
        now = datetime.now(UTC)
        mark = _minute_mark(now)
        elapsed = (now - mark).total_seconds()
        if elapsed >= minimum_seconds and elapsed <= _MAX_MINUTE_ELAPSED_SECONDS:
            return
        time.sleep(max(0.5, minimum_seconds - elapsed + 0.5))


def _minute_mark(now: datetime) -> datetime:
    return now.replace(second=0, microsecond=0)


def _next_due(revision: RoutineRevision, previous: datetime) -> datetime:
    return revision.next_fire_after(previous)


def _advance_trigger(tenant: TenantFixture, revision: RoutineRevision, due: datetime) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE routine_triggers AS trigger SET next_fire_at = %s
            FROM routine_revisions AS revision
            WHERE trigger.revision_digest = revision.revision_digest
              AND revision.routine_ref = %s AND trigger.tenant_id = %s
            """,
            (due, revision.routine_ref, tenant.tenant_id),
        )
        connection.commit()


def _create_open_ticket(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT ticket_id, custodian_principal_id, created_by "
            "FROM tickets WHERE tenant_id = %s LIMIT 1",
            (tenant.tenant_id,),
        ).fetchone()
        if row is not None:
            return
        now = datetime.now(UTC)
        ticket_id = uuid4()
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by,
                created_at, project_key, current_episode
            ) VALUES (%s, %s, 'Sentinel gate ticket', 'acceptance', 'rtn-sentinel', 'P1',
                      %s, 1, 'durability_pending', %s, %s, 'ctower', 1)
            """,
            (ticket_id, tenant.tenant_id, tenant.commander_id, tenant.operator_id, now),
        )
        connection.execute(
            """
            INSERT INTO lifecycle_episodes (ticket_id, tenant_id, episode_number, state, opened_at)
            VALUES (%s, %s, 1, 'open', %s)
            """,
            (ticket_id, tenant.tenant_id, now),
        )
        connection.commit()


def _append_event(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT stream_id, aggregate_id, sequence, request_sha256, prev_hash
            FROM events WHERE tenant_id = %s ORDER BY record_position DESC LIMIT 1
            """,
            (tenant.tenant_id,),
        ).fetchone()
        if row is None:
            raise AssertionError("movement gate needs at least one baseline event")
        now = datetime.now(UTC)
        position = connection.execute(
            "UPDATE record_position_ledger SET last_position = last_position + 1 "
            "WHERE singleton RETURNING last_position"
        ).fetchone()
        if position is None:
            raise AssertionError("record position ledger did not return a position")
        connection.execute(
            """
            INSERT INTO events (
                event_id, tenant_id, stream_id, aggregate_id, sequence, kind,
                schema_version, actor_principal_id, client_command_id, request_sha256,
                correlation_id, causation_id, origin, server_time, payload,
                prev_hash, event_hash, record_position
            ) VALUES (%s, %s, %s, %s, %s, 'ticket.comment_added', 1, %s, %s, %s,
                      %s, NULL, 'api', %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                tenant.tenant_id,
                row[0],
                row[1],
                int(row[2]) + 1,
                tenant.operator_id,
                uuid4(),
                row[3],
                uuid4(),
                now,
                json.dumps({"schema": "ctower.event/v1"}),
                row[4],
                row[4],
                position[0],
            ),
        )
        connection.commit()


def _table_counts(tenant: TenantFixture, *tables: str) -> dict[str, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts: dict[str, int] = {}
        for table in tables:
            query = _TABLE_COUNT_QUERIES.get(table)
            if query is None:
                raise AssertionError(f"unsupported table count: {table}")
            row = connection.execute(sql.SQL(query)).fetchone()
            if row is None:
                raise AssertionError(f"count query returned no row: {table}")
            counts[table] = int(row[0])
        return counts


def _replace_ref(revision: RoutineRevision, routine_ref: str) -> RoutineRevision:
    return replace(revision, routine_ref=routine_ref)
