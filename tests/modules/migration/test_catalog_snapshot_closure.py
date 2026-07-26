"""Signed Catalog checkpoint closure at the pass-two boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from ctower_kernel.record import RecordProblem
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    execute_import,
)

from . import test_postgres as spine
from ._checkpoint_truth import materialize_checkpoint_truth, refresh_checkpoint_truth
from ._postgres import Database, semantic_counts

__all__: tuple[str, ...] = ()


def test_changed_catalog_definition_refuses_pass_two_without_delta(
    migration_database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        spine,
        "materialize_checkpoint_truth",
        partial(
            materialize_checkpoint_truth,
            outcome_overrides={"I1.0": "changed after the signed source snapshot"},
        ),
    )
    context = spine._start_run(migration_database, tmp_path)
    importer, plan = spine._bind_reviewed_plan(context, migration_database)
    first = execute_import(
        plan,
        client=spine._MigrationClient(context.migration, importer),
        apply=True,
    )
    assert isinstance(first, ImportPassReceipt)
    refresh_checkpoint_truth(migration_database, now=datetime.now(UTC))

    before = _closure_state(migration_database, context.created.run_id)
    refused = context.migration.apply_batch(
        importer,
        plan.batches[0],
        telemetry=spine._telemetry(importer),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "migration-run-conflict"
    assert _closure_state(migration_database, context.created.run_id) == before

    with psycopg.connect(migration_database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT state,
                (SELECT count(*) FROM migration_import_pass_two_snapshots
                 WHERE run_id = %s)
            FROM migration_import_run_facts
            WHERE run_id = %s ORDER BY fact_sequence DESC LIMIT 1
            """,
            (context.created.run_id, context.created.run_id),
        ).fetchone()
    assert row == ("pass_one_complete", 0)


def _closure_state(database: Database, run_id: UUID) -> tuple[object, ...]:
    with psycopg.connect(database.admin_dsn) as connection:
        run_facts = connection.execute(
            """
            SELECT fact_sequence, state, semantic_digest, record_watermark,
                projection_watermark, event_id, command_id
            FROM migration_import_run_facts
            WHERE run_id = %s ORDER BY fact_sequence
            """,
            (run_id,),
        ).fetchall()
        credentials = connection.execute(
            """
            SELECT credential.revoked_at
            FROM principal_credentials AS credential
            JOIN migration_importer_bindings AS binding
              ON binding.tenant_id = credential.tenant_id
             AND binding.principal_id = credential.principal_id
             AND binding.credential_digest = credential.credential_digest
            WHERE binding.run_id = %s
            """,
            (run_id,),
        ).fetchall()
        credential_facts = connection.execute(
            """
            SELECT fact_sequence, lifecycle, command_id
            FROM migration_importer_credential_facts
            WHERE run_id = %s ORDER BY fact_sequence
            """,
            (run_id,),
        ).fetchall()
    return (
        semantic_counts(database),
        tuple(run_facts),
        tuple(credentials),
        tuple(credential_facts),
    )
