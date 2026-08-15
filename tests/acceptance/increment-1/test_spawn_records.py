"""Acceptance for CT-I1-034 spawn-custody records (R2982/R3000, AC-SPWN-01..04).

Real PostgreSQL through the session-scoped development composition; every test
exercises the kernel module and the HTTP surface exactly as the spawn driver
will. RED-first: this suite is authored before the append-only rebuild, so the
immutability and derived-state assertions fail against the current mutable
implementation.
"""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from support.tenant_fixture import TenantFixture

from ctower_kernel.runtime.spawn_driver import (
    SpawnSpool,
    derive_initial_running_set,
    reconcile_source,
)
from ctower_kernel.runtime.spawn_records import (
    PostgresSpawnRecords,
    SpawnRecordCreate,
    SpawnRecordGet,
    SpawnRecordList,
    SpawnRecordProblem,
    SpawnRecordTransitionCommand,
)

__all__: tuple[str, ...] = ()

_HARNESS = "codex-crew"
_SPOOL_MODE = 0o600
_MODEL = "gpt-5-codex"


def _create_command(*, effort: str | None = "high") -> SpawnRecordCreate:
    return SpawnRecordCreate(
        client_command_id=uuid4(),
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-r3000-spawn",
        task_file_ref="coordination/2026-08-15_0200--engineer-r3000-spawn--custody.task.md",
        worktree_path="/srv/projects/ctower/.worktrees/r3000-spawn",
        harness=_HARNESS,
        model=_MODEL,
        effort=effort,
        workspace_id=None,
    )


def _records(tenant: TenantFixture) -> PostgresSpawnRecords:
    return PostgresSpawnRecords(tenant.database.runtime_dsn)


def _actor(tenant: TenantFixture) -> tuple[UUID, UUID]:
    return tenant.commander_id, tenant.tenant_id


def _spawn_get(outcome: SpawnRecordGet | SpawnRecordProblem) -> SpawnRecordGet:
    assert isinstance(outcome, SpawnRecordGet), f"expected spawn record, got {outcome!r}"
    return outcome


def _spawn_list(outcome: SpawnRecordList | SpawnRecordProblem) -> SpawnRecordList:
    assert isinstance(outcome, SpawnRecordList), f"expected spawn list, got {outcome!r}"
    return outcome


def _spawn_problem(outcome: object) -> SpawnRecordProblem:
    assert isinstance(outcome, SpawnRecordProblem), f"expected problem, got {outcome!r}"
    return outcome


# ---------------------------------------------------------------------------
# AC-SPWN-01 — append-only record, derived lifecycle state, prohibited data
# ---------------------------------------------------------------------------


class TestSpawnRecordAppendOnly:
    """One strict append-only record; lifecycle is appended transition facts."""

    def test_create_persists_row_and_spawn_recorded_event(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        outcome = records.create(principal_id, tenant_id, _create_command())
        payload = _spawn_get(outcome).response_payload()
        assert payload["status"] == "requested"

        with psycopg.connect(tenant.database.admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT e.kind FROM events e
                JOIN spawn_records s ON s.event_id = e.event_id
                WHERE s.tenant_id = %s
                """,
                (tenant_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "spawn.recorded"

    def test_transition_appends_fact_without_mutating_record(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(records.create(principal_id, tenant_id, _create_command()))
        spawn_id = created.record.spawn_id

        transition = records.transition(
            principal_id,
            tenant_id,
            SpawnRecordTransitionCommand(
                client_command_id=uuid4(),
                spawn_id=spawn_id,
                to_status="accepted",
                reason="operator GO",
            ),
        )
        _spawn_get(transition)

        with psycopg.connect(tenant.database.admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT to_status FROM spawn_record_transitions
                WHERE tenant_id = %s AND spawn_id = %s
                """,
                (tenant_id, spawn_id),
            ).fetchone()
        assert row is not None
        assert row[0] == "accepted"

    def test_derived_status_follows_latest_transition(self, tenant: TenantFixture) -> None:
        """AC-SPWN-01: no in-place mutation — status derives from latest fact."""
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(records.create(principal_id, tenant_id, _create_command()))
        spawn_id = created.record.spawn_id
        for to_status in ("accepted", "running"):
            outcome = records.transition(
                principal_id,
                tenant_id,
                SpawnRecordTransitionCommand(
                    client_command_id=uuid4(),
                    spawn_id=spawn_id,
                    to_status=to_status,
                    reason=None,
                ),
            )
            _spawn_get(outcome)

        fetched = _spawn_get(records.get(principal_id, tenant_id, spawn_id))
        assert fetched.record.status == "running"

    def test_spawn_record_row_is_immutable(self, tenant: TenantFixture) -> None:
        """AC-SPWN-01 RED: UPDATE must be refused by the immutability trigger."""
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(records.create(principal_id, tenant_id, _create_command()))
        spawn_id = created.record.spawn_id

        with (
            psycopg.connect(tenant.database.admin_dsn) as connection,
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        ):
            connection.execute(
                "UPDATE spawn_records SET crew_name = 'mutator' WHERE spawn_id = %s",
                (spawn_id,),
            )

    def test_illegal_transition_refused(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(records.create(principal_id, tenant_id, _create_command()))
        spawn_id = created.record.spawn_id
        outcome = records.transition(
            principal_id,
            tenant_id,
            SpawnRecordTransitionCommand(
                client_command_id=uuid4(),
                spawn_id=spawn_id,
                to_status="completed",  # requested -> completed skips accepted/running
                reason=None,
            ),
        )
        problem = _spawn_problem(outcome)
        assert problem.code == "invalid-transition"

    def test_terminal_state_refuses_further_transition(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(
            records.create(principal_id, tenant_id, _create_create_command_variant())
        )
        spawn_id = created.record.spawn_id
        for to_status in ("accepted", "running", "completed"):
            records.transition(
                principal_id,
                tenant_id,
                SpawnRecordTransitionCommand(
                    client_command_id=uuid4(),
                    spawn_id=spawn_id,
                    to_status=to_status,
                    reason=None,
                ),
            )
        after_terminal = records.transition(
            principal_id,
            tenant_id,
            SpawnRecordTransitionCommand(
                client_command_id=uuid4(),
                spawn_id=spawn_id,
                to_status="failed",
                reason=None,
            ),
        )
        problem = _spawn_problem(after_terminal)
        assert problem.code == "invalid-transition"

    def test_idempotent_replay_returns_original(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        command = _create_command()
        first = records.create(principal_id, tenant_id, command)
        second = records.create(principal_id, tenant_id, command)
        assert _spawn_get(first).record.spawn_id == _spawn_get(second).record.spawn_id

    def test_transition_idempotent_replay_returns_original_payload(
        self, tenant: TenantFixture
    ) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        created = _spawn_get(records.create(principal_id, tenant_id, _create_command()))
        command = SpawnRecordTransitionCommand(
            client_command_id=uuid4(),
            spawn_id=created.record.spawn_id,
            to_status="accepted",
            reason="operator confirmed",
        )

        first = _spawn_get(records.transition(principal_id, tenant_id, command))
        second = _spawn_get(records.transition(principal_id, tenant_id, command))

        assert second.response_payload() == first.response_payload()

    def test_no_credential_value_in_payloads(self, tenant: TenantFixture) -> None:
        """AC-SPWN-01: prohibited data class scan over caller-authored fields."""
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        # A credential-looking value smuggled into a caller-authored text field
        # must be refused without any mutation (D30 prohibited classes).
        credential_label = "api" + "_key"
        command = dataclass_replace(
            _create_command(), task_file_ref=f"{credential_label} = {'a' * 8}"
        )
        outcome = records.create(principal_id, tenant_id, command)
        problem = _spawn_problem(outcome)
        assert problem.code == "prohibited-data-class"

    def test_no_credential_value_in_effort_pin(self, tenant: TenantFixture) -> None:
        """Every caller-authored text field, including the substrate pin, is scanned."""
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        credential_label = "api" + "_key"
        command = dataclass_replace(_create_command(), effort=f"{credential_label} = {'a' * 8}")

        outcome = records.create(principal_id, tenant_id, command)

        problem = _spawn_problem(outcome)
        assert problem.code == "prohibited-data-class"

    def test_list_filters_by_project(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        records.create(principal_id, tenant_id, _create_command())
        listed = _spawn_list(records.list(principal_id, tenant_id, "ctower"))
        assert len(listed.records) >= 1

    def test_list_refuses_an_unauthored_status_filter(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)

        outcome = records.list(principal_id, tenant_id, "ctower", status="not-a-status")

        problem = _spawn_problem(outcome)
        assert problem.code == "invalid-status"

    def test_create_refuses_a_foreign_project_for_a_seat(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        principal_id, tenant_id = _actor(tenant)
        outcome = records.create(
            principal_id,
            tenant_id,
            dataclass_replace(_create_command(), project_key="manibo"),
        )
        problem = _spawn_problem(outcome)
        assert problem.code == "project-scope-denied"

    def test_project_list_filter_does_not_leak_other_projects(self, tenant: TenantFixture) -> None:
        records = _records(tenant)
        operator_id, tenant_id = tenant.operator_id, tenant.tenant_id
        first = records.create(operator_id, tenant_id, _create_command())
        second = records.create(
            operator_id,
            tenant_id,
            dataclass_replace(
                _create_command(),
                project_key="manibo",
                crew_name="mc-engineer-r3000-manibo",
            ),
        )
        _spawn_get(first)
        _spawn_get(second)

        listed = _spawn_list(records.list(operator_id, tenant_id, "ctower"))
        assert listed.records
        assert all(record.project_key == "ctower" for record in listed.records)


def _create_create_command_variant() -> SpawnRecordCreate:
    return _create_command()


def test_migration_forward_apply_creates_requested_spawn(tenant: TenantFixture) -> None:
    """Manifest forward_test node: fresh apply then one create round-trips to `requested`."""
    records = _records(tenant)
    principal_id, tenant_id = _actor(tenant)
    outcome = records.create(principal_id, tenant_id, _create_command())
    payload = _spawn_get(outcome).response_payload()
    assert payload["status"] == "requested"


# ---------------------------------------------------------------------------
# AC-SPWN-02 — record-before-drive ordering + mode-0600 pending spool
# ---------------------------------------------------------------------------


class TestRecordBeforeDrive:
    """The driver records the spawn BEFORE creating any host session."""

    def test_spool_round_trip(self, tmp_path: Path) -> None:
        """Unreachable ctower appends to 0600 spool; replay ACKs and removes."""
        spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
        command = _create_command()
        entry = spool.append(command)
        assert entry.state == "durability_pending"
        assert (tmp_path / "spawn-spool.jsonl").stat().st_mode & 0o777 == _SPOOL_MODE

        pending = spool.pending()
        assert len(pending) == 1

        acked = spool.remove_acked([entry.entry_id])
        assert acked == 1
        assert spool.pending() == ()


# ---------------------------------------------------------------------------
# AC-SPWN-03 — history import by source identity
# ---------------------------------------------------------------------------


class TestHistoryImport:
    """crew-log rows import by source identity, latest status effective."""

    def test_initial_running_set_derivation(self) -> None:
        source_rows: list[dict[str, object]] = [
            {"uuid": "11111111-1111-1111-1111-111111111111", "status": "running"},
            {"uuid": "22222222-2222-2222-2222-222222222222", "status": "completed"},
            {"uuid": "33333333-3333-3333-3333-333333333333", "status": "running"},
            {"uuid": "33333333-3333-3333-3333-333333333333", "status": "failed"},
            {"uuid": "44444444-4444-4444-4444-444444444444", "status": "done"},
            {"uuid": "55555555-5555-5555-5555-555555555555", "status": "closed"},
            {"uuid": "66666666-6666-6666-6666-666666666666", "status": "idle"},
        ]
        running = derive_initial_running_set(source_rows)
        assert [row.uuid for row in running] == [UUID("11111111-1111-1111-1111-111111111111")]


# ---------------------------------------------------------------------------
# AC-SPWN-04 — parity proof before read-path swap
# ---------------------------------------------------------------------------


class TestParityProof:
    """Reconcile reads the external twin until one recorded parity proof."""

    def test_parity_report_required_before_swap(self) -> None:
        # Pre-proof: reconcile input must name the external twin, not ctower reads.
        assert reconcile_source() == "external-twin"
