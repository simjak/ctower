"""Current authoritative-target drift refusal evidence."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from ctower_client.models import CtowerProjectImportFinalizeRequest, CtowerProjectImportRun
from ctower_kernel.migration import Migration
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

from ._postgres import Database, semantic_counts

__all__ = ["assert_live_target_drift_refusal"]


class _RunContext(Protocol):
    @property
    def migration(self) -> Migration: ...

    @property
    def operator(self) -> Actor: ...


def assert_live_target_drift_refusal(
    context: _RunContext,
    database: Database,
    run: CtowerProjectImportRun,
    artifact: str,
) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT checkpoint_key, row_payload
            FROM project_delivery_projection_rows
            WHERE tenant_id = %s AND project_key = 'ctower'
            ORDER BY checkpoint_key LIMIT 1
            """,
            (database.tenant_id,),
        ).fetchone()
        assert row is not None
        checkpoint_key, original = str(row[0]), row[1]
        connection.execute(
            """
            UPDATE project_delivery_projection_rows
            SET row_payload = row_payload || '{"g3_forced_drift": true}'::jsonb
            WHERE tenant_id = %s AND project_key = 'ctower' AND checkpoint_key = %s
            """,
            (database.tenant_id, checkpoint_key),
        )
    before = semantic_counts(database)
    refused = context.migration.finalize_run(
        context.operator,
        CtowerProjectImportFinalizeRequest(
            run_id=run.run_id,
            cutover_id=run.cutover_id,
            expected_run_semantic_digest=run.semantic_digest,
            reconciliation_artifact=artifact,
        ),
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "migration-import-finalization-refused"
    assert semantic_counts(database) == before
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE project_delivery_projection_rows SET row_payload = %s
            WHERE tenant_id = %s AND project_key = 'ctower' AND checkpoint_key = %s
            """,
            (Jsonb(original), database.tenant_id, checkpoint_key),
        )


def _telemetry(actor: Actor) -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=command_id,
    )
