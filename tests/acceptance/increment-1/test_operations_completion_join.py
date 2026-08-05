"""PostgreSQL acceptance for the Routine concurrency pending-jobs completion join (gh#145)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from support.acceptance import accept_command
from support.tenant_fixture import TenantFixture

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    FixedOperationCompletion,
    FixedOperations,
    Routine,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()


def test_completed_job_stops_coalescing_the_next_due_occurrence(
    tenant: TenantFixture,
) -> None:
    runtime_store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(runtime_store)
    fixed = FixedOperations(runtime_store)
    revision = RoutineRevision(
        routine_ref="ctower.test.completion-join@1",
        revision_digest="sha256:" + "e" * 64,
        schedule_kind=ScheduleKind.HOURLY,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.COALESCE_IF_ACTIVE,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="synthetic_four_stage",
        timeout_seconds=60,
        component_digests=("sha256:" + "f" * 64,),
    )
    first_fire = datetime.now(UTC) - timedelta(hours=2)

    runtime.register(tenant.tenant_id, revision, first_fire_at=first_fire)
    first = runtime.scan(tenant.tenant_id)
    assert len(first.jobs) == 1
    first_job_id = first.jobs[0].job_id

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        occurrence = connection.execute(
            """
            SELECT actor_principal_id, client_command_id
            FROM routine_occurrences
            WHERE tenant_id = %s AND revision_digest = %s AND outcome = 'queued'
            """,
            (tenant.tenant_id, bytes.fromhex("e" * 64)),
        ).fetchone()
    assert occurrence is not None
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        cast(UUID, occurrence["actor_principal_id"]),
        cast(UUID, occurrence["client_command_id"]),
    )

    attempt = fixed.claim_synthetic("ctower.test.completion-join")
    assert attempt is not None
    assert attempt.job.job_id == first_job_id
    fixed.complete_synthetic(
        attempt,
        FixedOperationCompletion(
            succeeded=False,
            ticket_id=None,
            lifecycle_facts=(),
            detail_code="synthetic-test-complete",
        ),
    )

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE routine_triggers SET next_fire_at = %s
            WHERE tenant_id = %s AND revision_digest = %s
            """,
            (datetime.now(UTC), tenant.tenant_id, bytes.fromhex("e" * 64)),
        )

    second = runtime.scan(tenant.tenant_id)

    assert len(second.jobs) == 1
    assert second.jobs[0].job_id != first_job_id
