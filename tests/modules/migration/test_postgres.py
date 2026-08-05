"""Real PostgreSQL proof for the reviewed migration truth spine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg.rows import dict_row

from ctower_client.models import (
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectReconciliationResult,
)
from ctower_kernel.migration import Migration, PostgresMigration, _pass_two_graph, _pass_two_sql
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    execute_import,
    prove_pass_two,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import ImportPlan
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner

from ._checkpoint_truth import materialize_checkpoint_truth, refresh_checkpoint_truth
from ._correction_evidence import assert_append_only_corrections
from ._postgres import Database, semantic_counts
from ._review_graph_evidence import (
    assert_export_graph_refusals,
    assert_plan_graph_refusals,
)
from ._reviewed import ReviewedSource, reviewed_source
from ._target_drift_evidence import assert_live_target_drift_refusal
from .source_tool.fixtures import CUTOVER_ID, REVIEW

_OPERATION_COUNT = 98
_REQUEST_PHYSICAL_COUNT = 243
__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _RunContext:
    now: datetime
    source: ReviewedSource
    store: PostgresMigration
    migration: Migration
    operator: Actor
    created: CtowerProjectImportRun
    credential_digest: bytes
    alternate_signer: ArtifactSigner


def test_complete_reviewed_two_pass_is_measured_and_partial_finalize_refuses(
    migration_database: Database,
    tmp_path: Path,
) -> None:
    context = _start_run(migration_database, tmp_path)
    importer, plan = _bind_reviewed_plan(context, migration_database)
    first_batch = _apply_first_and_refuse_partial(
        context,
        migration_database,
        importer,
        plan,
    )
    assert_append_only_corrections(context, migration_database, plan, first_batch)
    ready = _finish_two_pass(
        context,
        migration_database,
        importer,
        plan,
        first_batch,
    )
    _assert_reconciliation_refusals(context, migration_database, ready)
    artifact = _reconciliation_artifact(context, ready)
    _assert_finalize_replay(context, migration_database, ready, artifact)


def _finish_two_pass(
    context: _RunContext,
    database: Database,
    importer: Actor,
    plan: ImportPlan,
    first_batch: CtowerProjectImportBatchResult,
) -> CtowerProjectImportRun:
    first = execute_import(
        plan,
        client=_MigrationClient(context.migration, importer),
        apply=True,
        completed=(first_batch,),
    )
    refresh_checkpoint_truth(database, now=datetime.now(UTC))
    second = execute_import(
        plan,
        client=_MigrationClient(context.migration, importer),
        apply=True,
    )
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    prove_pass_two(first, second)
    ready = context.migration.get_run(context.operator, context.created.run_id)
    assert not isinstance(ready, RecordProblem)
    _assert_measured(ready)
    _assert_phase_and_measurement_rows(database, ready.run_id)
    return ready


def _assert_finalize_replay(
    context: _RunContext,
    database: Database,
    ready: CtowerProjectImportRun,
    artifact: str,
) -> None:
    finalize = _finalize(ready, artifact)
    command_id = uuid4()
    result = context.migration.finalize_run(
        context.operator,
        finalize,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    _assert_finalized(
        result,
        ready,
        context.store,
        context.credential_digest,
        context.now,
    )
    before_replay = semantic_counts(database)
    assert (
        context.migration.finalize_run(
            context.operator,
            finalize,
            command_id=command_id,
            telemetry=_telemetry(context.operator),
        )
        == result
    )
    assert semantic_counts(database) == before_replay
    _assert_exact_reconciliation_bytes(database, ready.run_id, artifact)
    changed = finalize.model_copy(
        update={"reconciliation_artifact": _reconciliation_artifact(context, ready)}
    )
    drifted = context.migration.finalize_run(
        context.operator,
        changed,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(drifted, RecordProblem)
    assert drifted.code == "migration-operation-drift"
    assert semantic_counts(database) == before_replay


def test_canonical_importer_revocation_refuses_preparsed_actor_without_delta(
    migration_database: Database,
    tmp_path: Path,
) -> None:
    context = _start_run(migration_database, tmp_path)
    importer, plan = _bind_reviewed_plan(context, migration_database)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        changed = connection.execute(
            """
            UPDATE principal_credentials
            SET revoked_at = %s
            WHERE tenant_id = %s AND principal_id = %s
              AND credential_digest = %s AND revoked_at IS NULL
            """,
            (
                datetime.now(UTC),
                importer.tenant_id,
                importer.principal_id,
                context.credential_digest,
            ),
        )
        assert changed.rowcount == 1
    assert (
        context.store.resolve_importer_credential(
            context.credential_digest,
            context.now,
        )
        is None
    )
    before = semantic_counts(migration_database)
    refused = context.migration.apply_batch(
        importer,
        plan.batches[0],
        telemetry=_telemetry(importer),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "migration-capability-denied"
    assert semantic_counts(migration_database) == before


def test_unexpected_run_source_link_blocks_pass_two_with_exact_identity(
    migration_database: Database,
    tmp_path: Path,
) -> None:
    context = _start_run(migration_database, tmp_path)
    importer, plan = _bind_reviewed_plan(context, migration_database)
    first = execute_import(
        plan,
        client=_MigrationClient(context.migration, importer),
        apply=True,
    )
    assert isinstance(first, ImportPassReceipt)
    refresh_checkpoint_truth(migration_database, now=datetime.now(UTC))
    link_id = uuid4()
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO migration_source_link_revisions (
                link_id, revision, run_id, namespace, immutable_source_id,
                link_class, target_kind, target_id, reason_code, semantic_digest,
                supersedes_revision, command_id, recorded_at
            ) VALUES (%s, 1, %s, 'unexpected', 'test-extra-source',
                'provenance', 'decision', 'decision:unexpected',
                'unexpected.source', %s, NULL, %s, %s)
            """,
            (
                link_id,
                context.created.run_id,
                hashlib.sha256(b"unexpected-source-link").digest(),
                link_id,
                context.now,
            ),
        )
    with psycopg.connect(migration_database.admin_dsn, row_factory=dict_row) as connection:
        measured = _pass_two_graph.graph(
            _pass_two_sql.capture(connection, context.created.run_id).body
        )
    assert measured["unexpected"] == [
        "source_link:unexpected:test-extra-source",
    ]
    before = semantic_counts(migration_database)
    refused = context.migration.apply_batch(
        importer,
        plan.batches[0],
        telemetry=_telemetry(importer),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "migration-run-conflict"
    assert semantic_counts(migration_database) == before


def _start_run(database: Database, tmp_path: Path) -> _RunContext:
    now = datetime.now(UTC)
    materialize_checkpoint_truth(database, now=now)
    source = reviewed_source(tmp_path, CUTOVER_ID)
    alternate_private = Ed25519PrivateKey.generate()
    alternate_signer = ArtifactSigner(
        "signing-key-ref:test/alternate-reviewer",
        1,
        alternate_private,
    )
    store = PostgresMigration(
        database.runtime_dsn,
        trusted_reviewer_keys={
            **source.trusted_keys,
            ("signing-key-ref:test/alternate-reviewer", 1): (alternate_private.public_key()),
        },
    )
    migration = Migration(store, clock=lambda: now)
    operator = Actor(database.operator_id, database.tenant_id, PrincipalKind.OPERATOR)
    request = source.create_request(now)
    before = semantic_counts(database)
    for candidate, candidate_request in (
        (Migration(PostgresMigration(database.runtime_dsn), clock=lambda: now), request),
        (
            migration,
            request.model_copy(update={"source_selection_digest": f"sha256:{'0' * 64}"}),
        ),
        (
            migration,
            request.model_copy(
                update={
                    "source_selection_artifact": _resign(
                        alternate_signer,
                        request.source_selection_artifact,
                        "manifest_digest",
                    )
                }
            ),
        ),
    ):
        refused = candidate.create_run(
            operator,
            candidate_request,
            command_id=uuid4(),
            telemetry=_telemetry(operator),
        )
        assert isinstance(refused, RecordProblem)
        assert semantic_counts(database) == before
    created = migration.create_run(
        operator,
        request,
        command_id=uuid4(),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(created, RecordProblem)
    credential_digest = hashlib.sha256(source.importer_credential.encode()).digest()
    assert store.resolve_importer_credential(credential_digest, now) is None
    return _RunContext(
        now,
        source,
        store,
        migration,
        operator,
        created,
        credential_digest,
        alternate_signer,
    )


def _bind_reviewed_plan(
    context: _RunContext,
    database: Database,
) -> tuple[Actor, ImportPlan]:
    assert_export_graph_refusals(context, database)
    exported = context.migration.bind_export_equality(
        context.operator,
        context.source.export_request(context.created.run_id),
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert not isinstance(exported, RecordProblem)
    plan_request, plan = context.source.plan_request(
        context.created.run_id,
        _create_target(database, context.operator),
        database.commander_id,
        context.now,
    )
    assert_plan_graph_refusals(context, database, plan_request)
    planned = context.migration.bind_alias_plan(
        context.operator,
        plan_request,
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert not isinstance(planned, RecordProblem)
    importer = context.store.resolve_importer_credential(
        context.credential_digest,
        context.now,
    )
    assert importer is not None
    assert (
        context.store.resolve_importer(
            context.credential_digest,
            context.created.run_id,
            context.created.cutover_id,
            "ctower",
            context.now,
        )
        == importer
    )
    assert (
        context.store.resolve_importer(
            context.credential_digest,
            context.created.run_id,
            context.created.cutover_id,
            "another-project",
            context.now,
        )
        is None
    )
    return importer, plan


def _resign(
    signer: ArtifactSigner,
    artifact_text: str,
    digest_field: str,
) -> str:
    artifact = json.loads(artifact_text)
    body = {key: value for key, value in artifact.items() if key not in {digest_field, "signature"}}
    return canonical_bytes(signer.seal(body, digest_field)).decode()


def _apply_first_and_refuse_partial(
    context: _RunContext,
    database: Database,
    importer: Actor,
    plan: ImportPlan,
) -> CtowerProjectImportBatchResult:
    before_out_of_order = semantic_counts(database)
    out_of_order = context.migration.apply_batch(
        importer,
        plan.batches[1],
        telemetry=_telemetry(importer),
    )
    assert isinstance(out_of_order, RecordProblem)
    denied = context.migration.apply_batch(
        context.operator,
        plan.batches[0],
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(denied, RecordProblem)
    assert semantic_counts(database) == before_out_of_order
    changed = plan.batches[0].model_copy(
        update={"operations": tuple(reversed(plan.batches[0].operations))}
    )
    before_changed = semantic_counts(database)
    rejected = context.migration.apply_batch(
        importer,
        changed,
        telemetry=_telemetry(importer),
    )
    assert isinstance(rejected, RecordProblem)
    assert semantic_counts(database) == before_changed
    first_batch = context.migration.apply_batch(
        importer,
        plan.batches[0],
        telemetry=_telemetry(importer),
    )
    assert not isinstance(first_batch, RecordProblem)
    before_premature_replay = semantic_counts(database)
    premature_replay = context.migration.apply_batch(
        importer,
        plan.batches[0],
        telemetry=_telemetry(importer),
    )
    assert isinstance(premature_replay, RecordProblem)
    assert premature_replay.code == "migration-run-conflict"
    assert semantic_counts(database) == before_premature_replay
    partial = context.migration.get_run(context.operator, context.created.run_id)
    assert not isinstance(partial, RecordProblem)
    before_finalize = semantic_counts(database)
    partial_result = context.migration.finalize_run(
        context.operator,
        _finalize(partial),
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(partial_result, RecordProblem)
    assert semantic_counts(database) == before_finalize
    return first_batch


class _MigrationClient:
    def __init__(self, migration: Migration, importer: Actor) -> None:
        self._migration = migration
        self._importer = importer

    def apply_ctower_project_import_batch(
        self,
        request: CtowerProjectImportBatchRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportBatchResult:
        outcome = self._migration.apply_batch(
            self._importer,
            request,
            command_id=command_id,
            telemetry=_telemetry(self._importer),
        )
        assert not isinstance(outcome, RecordProblem)
        return outcome


def _assert_measured(ready: CtowerProjectImportRun) -> None:
    assert ready.state == "pass_two_noop"
    assert ready.counts.planned_operations == ready.counts.applied_operations == _OPERATION_COUNT
    assert ready.counts.replayed_operations == _OPERATION_COUNT
    assert ready.conservation is not None
    assert ready.conservation.selected_request_physical_snapshots == _REQUEST_PHYSICAL_COUNT
    assert ready.conservation.pass_two_new_events == 0


def _assert_phase_and_measurement_rows(database: Database, run_id: UUID) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        states = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT state FROM migration_import_run_facts
                WHERE run_id = %s ORDER BY fact_sequence
                """,
                (run_id,),
            ).fetchall()
        ]
        snapshots = connection.execute(
            """
            SELECT boundary, snapshot_digest, snapshot_body, domain_fact_count,
                event_count, outbox_count, record_position, project_delivery_digest
            FROM migration_import_pass_two_snapshots
            WHERE run_id = %s ORDER BY boundary
            """,
            (run_id,),
        ).fetchall()
        replay_rows = connection.execute(
            """
            SELECT new_domain_facts, new_events, new_outbox_rows,
                record_position_delta, projection_semantic_delta
            FROM migration_import_replay_receipts
            WHERE run_id = %s ORDER BY batch_index
            """,
            (run_id,),
        ).fetchall()
    assert states[-3:] == [
        "pass_one_complete",
        "pass_two_started",
        "pass_two_noop",
    ]
    assert [str(row[0]) for row in snapshots] == ["end", "start"]
    end, start = snapshots
    assert bytes(end[1]) == bytes(start[1])
    assert end[2] == start[2]
    assert tuple(end[3:]) == tuple(start[3:])
    assert replay_rows
    assert all(tuple(int(value) for value in row) == (0, 0, 0, 0, 0) for row in replay_rows)


def _assert_reconciliation_refusals(
    context: _RunContext,
    database: Database,
    ready: CtowerProjectImportRun,
) -> None:
    accepted = _reconciliation_artifact(context, ready)
    assert_live_target_drift_refusal(context, database, ready, accepted)
    missing = json.loads(accepted)
    missing["actual_graph"]["stable_aliases"].pop()
    missing_artifact = _resign(
        context.source.fixture.signer,
        canonical_bytes(missing).decode(),
        "report_digest",
    )
    alternate_artifact = _resign(
        context.alternate_signer,
        accepted,
        "report_digest",
    )
    for artifact in (missing_artifact, alternate_artifact):
        before = semantic_counts(database)
        refused = context.migration.finalize_run(
            context.operator,
            _finalize(ready, artifact),
            command_id=uuid4(),
            telemetry=_telemetry(context.operator),
        )
        assert isinstance(refused, RecordProblem)
        assert refused.code == "migration-import-finalization-refused"
        assert semantic_counts(database) == before


def _assert_exact_reconciliation_bytes(
    database: Database,
    run_id: UUID,
    artifact: str,
) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT verified.artifact_canonical_bytes,
                reconciliation.report_canonical_bytes,
                reconciliation.report_body
            FROM migration_verified_artifacts AS verified
            JOIN migration_reconciliation_facts AS reconciliation
              ON reconciliation.run_id = verified.run_id
             AND reconciliation.report_digest = verified.artifact_digest
            WHERE verified.run_id = %s AND verified.artifact_kind = 'reconciliation'
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    expected = artifact.encode()
    assert bytes(row[0]) == expected
    assert bytes(row[1]) == expected
    assert row[2] == json.loads(artifact)


def _assert_finalized(
    result: object,
    ready: CtowerProjectImportRun,
    store: PostgresMigration,
    credential_digest: bytes,
    now: datetime,
) -> None:
    assert not isinstance(result, RecordProblem)
    assert isinstance(result, CtowerProjectReconciliationResult)
    assert result.expected_graph == ready.reconciliation_graph
    assert result.actual_graph == ready.reconciliation_graph
    assert result.pass_two_measurement == ready.pass_two_measurement
    assert result.target_semantic_digest == ready.semantic_digest
    assert store.resolve_importer_credential(credential_digest, now) is None


def _create_target(database: Database, operator: Actor) -> UUID:
    outcome = Work(PostgresRecord(database.runtime_dsn)).create_ticket(
        operator,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=database.commander_id,
            priority="P2",
            project_key="ctower",
            source=SourceReference("synthetic", "synthetic:alias-target"),
            title="Existing exact alias target",
        ),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _finalize(
    run: CtowerProjectImportRun,
    artifact: str = "{}",
) -> CtowerProjectImportFinalizeRequest:
    return CtowerProjectImportFinalizeRequest(
        run_id=run.run_id,
        cutover_id=run.cutover_id,
        expected_run_semantic_digest=run.semantic_digest,
        reconciliation_artifact=artifact,
    )


def _reconciliation_artifact(
    context: _RunContext,
    run: CtowerProjectImportRun,
) -> str:
    assert run.reconciliation_graph is not None
    assert run.pass_two_measurement is not None
    artifact = {
        "schema": "ctower.ctower-project-reconciliation/v2",
        "reconciliation_id": str(uuid4()),
        "run_id": str(run.run_id),
        "cutover_id": str(run.cutover_id),
        "project_key": "ctower",
        "pinned_digests": run.pinned_digests.model_dump(mode="json", by_alias=True),
        "reviewer_key": run.reviewer_key.model_dump(mode="json"),
        "expected_graph": run.reconciliation_graph.model_dump(mode="json"),
        "actual_graph": run.reconciliation_graph.model_dump(mode="json"),
        "pass_two_measurement": run.pass_two_measurement.model_dump(mode="json"),
        "watermarks": {
            "source_native": run.source_native_watermark,
            "export_native": run.export_native_watermark,
            "record_position": run.record_watermark,
            "projection_position": run.projection_watermark,
        },
        "target_semantic_digest": run.semantic_digest,
        "reconciled_at": REVIEW["reviewed_at"],
        "review": REVIEW,
        "durability_state": "durability_pending",
        "accepted_position": None,
    }
    return canonical_bytes(context.source.fixture.signer.seal(artifact, "report_digest")).decode()


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
