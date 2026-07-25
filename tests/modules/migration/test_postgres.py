"""PostgreSQL threat tests for the dormant restricted importer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    MigrationCorrectionRevision,
    MigrationRelationCorrection,
    MigrationSourceLinkCorrection,
)
from ctower_kernel.access import Access
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    Record,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import (
    PostgresRecord,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

from ._import_vectors import (
    ZERO_DIGEST,
)
from ._import_vectors import (
    alias_batch as _alias_batch,
)
from ._import_vectors import (
    batch as _batch,
)
from ._import_vectors import (
    relation_batch as _relation_batch,
)
from ._import_vectors import (
    run_request as _run_request,
)
from ._import_vectors import (
    seed_batch as _seed_batch,
)
from ._import_vectors import (
    source_link_batch as _source_link_batch,
)
from ._import_vectors import (
    ticket_seed as _ticket_seed,
)
from ._postgres import (
    Database as _Database,
)
from ._postgres import (
    relation_digest as _relation_digest,
)
from ._postgres import (
    semantic_counts as _semantic_counts,
)
from ._postgres import (
    source_link_digest as _source_link_digest,
)

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ImportContext:
    database: _Database
    now: datetime
    credential: str
    store: PostgresMigration
    migration: Migration
    operator: Actor
    run: CtowerProjectImportRun
    importer: Actor
    access: Access


def test_importer_is_run_scoped_replay_safe_and_database_guarded(
    migration_database: _Database,
) -> None:
    context = _start_import(migration_database)
    _assert_scope_and_guards(context)
    _bind_run(
        context.migration,
        context.operator,
        context.run.run_id,
        context.run.cutover_id,
    )
    ticket_a, ticket_b = _apply_seed_and_replay(context)
    relation_id, link_batch = _apply_alias_relation_links(context, ticket_a, ticket_b)
    _assert_invalid_link_correction(context, link_batch)
    _assert_correction_and_stale_refusal(context, relation_id)
    _assert_reconciliation_revokes_importer(context, link_batch)


def _start_import(database: _Database) -> _ImportContext:
    now = datetime.now(UTC)
    credential = "synthetic-importer-credential"
    store = PostgresMigration(database.runtime_dsn)
    migration = Migration(store, clock=lambda: now)
    operator = Actor(
        database.operator_id,
        database.tenant_id,
        PrincipalKind.OPERATOR,
    )
    request = _run_request(credential, now)
    created = migration.create_run(
        operator, request, command_id=uuid4(), telemetry=_telemetry(operator)
    )
    assert not isinstance(created, RecordProblem)
    importer = store.resolve_importer(
        hashlib.sha256(credential.encode()).digest(),
        created.run_id,
        created.cutover_id,
        "ctower",
        now,
    )
    assert importer is not None
    access = Access(
        cast(Record, _NoGeneralCredential()),
        importer_resolver=store.resolve_importer,
        clock=lambda: now,
    )
    return _ImportContext(
        database, now, credential, store, migration, operator, created, importer, access
    )


def _assert_scope_and_guards(context: _ImportContext) -> None:
    digest = hashlib.sha256(context.credential.encode()).digest()
    assert (
        context.store.resolve_importer(
            digest,
            context.run.run_id,
            uuid4(),
            "ctower",
            context.now,
        )
        is None
    )
    assert (
        context.store.resolve_importer(
            digest,
            context.run.run_id,
            context.run.cutover_id,
            "other",
            context.now,
        )
        is None
    )
    general = context.access.authenticate(f"Bearer {context.credential}")
    assert isinstance(general, RecordProblem)
    assert general.code == "unauthorized"
    assert (
        context.access.authenticate_importer(
            f"Bearer {context.credential}",
            run_id=context.run.run_id,
            cutover_id=context.run.cutover_id,
            project_key="ctower",
        )
        == context.importer
    )
    _assert_database_event_guard(context.database, context.importer)
    _assert_run_is_immutable(context.database, context.run.run_id)


def _apply_seed_and_replay(context: _ImportContext) -> tuple[UUID, UUID]:
    first = _seed_batch(
        context.run.run_id,
        context.run.cutover_id,
        context.database.commander_id,
        batch_index=0,
    )
    applied = context.migration.apply_batch(
        context.importer, first, telemetry=_telemetry(context.importer)
    )
    assert not isinstance(applied, RecordProblem)
    ticket_a, ticket_b = (UUID(result.target_id) for result in applied.results)
    before_replay = _semantic_counts(context.database)
    replayed = context.migration.apply_batch(
        context.importer, first, telemetry=_telemetry(context.importer)
    )
    assert not isinstance(replayed, RecordProblem)
    assert all(result.replayed for result in replayed.results)
    assert _semantic_counts(context.database) == before_replay
    changed = first.model_copy(
        update={
            "operations": (
                first.operations[0].model_copy(update={"title": "Changed replay"}),
                first.operations[1],
            )
        }
    )
    assert isinstance(
        context.migration.apply_batch(
            context.importer, changed, telemetry=_telemetry(context.importer)
        ),
        RecordProblem,
    )
    assert _semantic_counts(context.database) == before_replay
    _assert_crash_rollback(
        context.database,
        context.migration,
        context.importer,
        context.run.run_id,
        context.run.cutover_id,
    )
    _assert_cross_tenant_refused(context, first)
    return ticket_a, ticket_b


def _apply_alias_relation_links(
    context: _ImportContext, ticket_a: UUID, ticket_b: UUID
) -> tuple[UUID, CtowerProjectImportBatchRequest]:
    alias_ticket = _create_operator_ticket(context.database, context.operator)
    alias_batch = _alias_batch(
        context.run.run_id, context.run.cutover_id, alias_ticket, batch_index=1
    )
    assert not isinstance(
        context.migration.apply_batch(
            context.importer, alias_batch, telemetry=_telemetry(context.importer)
        ),
        RecordProblem,
    )
    _assert_alias_fork_refused(context, ticket_a)
    relation_id = uuid4()
    relation_batch = _relation_batch(
        context.run.run_id,
        context.run.cutover_id,
        relation_id,
        ticket_a,
        ticket_b,
        batch_index=2,
    )
    assert not isinstance(
        context.migration.apply_batch(
            context.importer, relation_batch, telemetry=_telemetry(context.importer)
        ),
        RecordProblem,
    )
    _assert_cycle_refused(context, ticket_a, ticket_b)
    link_batch = _source_link_batch(
        context.run.run_id, context.run.cutover_id, ticket_a, batch_index=3
    )
    assert not isinstance(
        context.migration.apply_batch(
            context.importer, link_batch, telemetry=_telemetry(context.importer)
        ),
        RecordProblem,
    )
    return relation_id, link_batch


def _bind_run(migration: Migration, operator: Actor, run_id: UUID, cutover_id: UUID) -> None:
    equality = CtowerProjectExportEqualityBindRequest(
        run_id=run_id,
        cutover_id=cutover_id,
        selection_digest=ZERO_DIGEST,
        inventory_a_digest=ZERO_DIGEST,
        inventory_b_digest=ZERO_DIGEST,
        export_digest=ZERO_DIGEST,
        equality_report_digest=ZERO_DIGEST,
        reviewer_public_key_digest=ZERO_DIGEST,
        result="equal",
    )
    exported = migration.bind_export_equality(
        operator, equality, command_id=uuid4(), telemetry=_telemetry(operator)
    )
    assert not isinstance(exported, RecordProblem)
    alias = CtowerProjectAliasPlanBindRequest(
        run_id=run_id,
        cutover_id=cutover_id,
        export_equality_digest=ZERO_DIGEST,
        alias_map_digest=ZERO_DIGEST,
        reviewer_public_key_digest=ZERO_DIGEST,
        attention_required=0,
    )
    bound = migration.bind_alias_plan(
        operator, alias, command_id=uuid4(), telemetry=_telemetry(operator)
    )
    assert not isinstance(bound, RecordProblem)
    assert bound.state == "alias_plan_bound"


def _assert_crash_rollback(
    database: _Database,
    migration: Migration,
    importer: Actor,
    run_id: UUID,
    cutover_id: UUID,
) -> None:
    seed = _ticket_seed("crash-seed", database.commander_id)
    invalid_link = _source_link_batch(run_id, cutover_id, uuid4(), batch_index=1).operations[0]
    request = _batch(run_id, cutover_id, 1, (seed, invalid_link))
    before = _semantic_counts(database)
    outcome = migration.apply_batch(importer, request, telemetry=_telemetry(importer))
    assert isinstance(outcome, RecordProblem)
    assert _semantic_counts(database) == before


def _assert_cross_tenant_refused(
    context: _ImportContext, request: CtowerProjectImportBatchRequest
) -> None:
    foreign = Actor(
        context.importer.principal_id,
        uuid4(),
        PrincipalKind.MIGRATION_IMPORTER,
    )
    next_batch = request.model_copy(update={"batch_index": 1})
    before = _semantic_counts(context.database)
    outcome = context.migration.apply_batch(foreign, next_batch, telemetry=_telemetry(foreign))
    assert isinstance(outcome, RecordProblem)
    assert _semantic_counts(context.database) == before


def _assert_alias_fork_refused(context: _ImportContext, ticket_id: UUID) -> None:
    fork = _alias_batch(
        context.run.run_id,
        context.run.cutover_id,
        ticket_id,
        batch_index=2,
    )
    before = _semantic_counts(context.database)
    outcome = context.migration.apply_batch(
        context.importer, fork, telemetry=_telemetry(context.importer)
    )
    assert isinstance(outcome, RecordProblem)
    assert _semantic_counts(context.database) == before


def _assert_cycle_refused(
    context: _ImportContext,
    ticket_a: UUID,
    ticket_b: UUID,
) -> None:
    cycle = _relation_batch(
        context.run.run_id,
        context.run.cutover_id,
        uuid4(),
        ticket_b,
        ticket_a,
        batch_index=3,
    )
    before = _semantic_counts(context.database)
    outcome = context.migration.apply_batch(
        context.importer, cycle, telemetry=_telemetry(context.importer)
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "migration-relation-invalid"
    assert _semantic_counts(context.database) == before


def _assert_correction_and_stale_refusal(
    context: _ImportContext,
    relation_id: UUID,
) -> None:
    current_digest = _relation_digest(context.database, relation_id)
    request = CtowerProjectImportCorrectionRequest(
        schema_id="ctower.ctower-project-import-correction/v1",
        correction_id=uuid4(),
        run_id=context.run.run_id,
        cutover_id=context.run.cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        correction_kind="relation",
        superseded_revision=MigrationCorrectionRevision(object_id=relation_id, revision=1),
        expected_current_digest=current_digest,
        replacement=MigrationRelationCorrection(
            kind="relation",
            superseded_relation_active=False,
            replacement_relation_id=None,
        ),
        reason="Reviewed relation correction",
        reviewer_id=context.operator.principal_id,
    )
    command_id = uuid4()
    receipt = context.migration.append_correction(
        context.operator,
        request,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    assert not isinstance(receipt, RecordProblem)
    before = _semantic_counts(context.database)
    replay = context.migration.append_correction(
        context.operator,
        request,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    assert replay == receipt
    assert _semantic_counts(context.database) == before
    stale = request.model_copy(update={"correction_id": uuid4()})
    outcome = context.migration.append_correction(
        context.operator,
        stale,
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "migration-correction-conflict"
    assert _semantic_counts(context.database) == before


def _assert_invalid_link_correction(
    context: _ImportContext,
    link_batch: CtowerProjectImportBatchRequest,
) -> None:
    link_id = link_batch.operations[0].identity.command_id
    request = CtowerProjectImportCorrectionRequest(
        schema_id="ctower.ctower-project-import-correction/v1",
        correction_id=uuid4(),
        run_id=context.run.run_id,
        cutover_id=context.run.cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        correction_kind="source_link",
        superseded_revision=MigrationCorrectionRevision(
            object_id=link_id,
            revision=1,
        ),
        expected_current_digest=_source_link_digest(context.database, link_id),
        replacement=MigrationSourceLinkCorrection(
            kind="source_link",
            target_kind="ticket",
            target_id=f"ticket:{uuid4()}",
            disposition="provenance_only",
        ),
        reason="Synthetic cross-scope target",
        reviewer_id=context.operator.principal_id,
    )
    before = _semantic_counts(context.database)
    outcome = context.migration.append_correction(
        context.operator,
        request,
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "migration-correction-conflict"
    assert _semantic_counts(context.database) == before


def _assert_reconciliation_revokes_importer(
    context: _ImportContext,
    next_batch: CtowerProjectImportBatchRequest,
) -> None:
    current = context.migration.get_run(context.operator, context.run.run_id)
    assert not isinstance(current, RecordProblem)
    request = CtowerProjectImportFinalizeRequest(
        run_id=context.run.run_id,
        cutover_id=context.run.cutover_id,
        expected_run_semantic_digest=current.semantic_digest,
    )
    command_id = uuid4()
    result = context.migration.finalize_run(
        context.operator,
        request,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    assert not isinstance(result, RecordProblem)
    before = _semantic_counts(context.database)
    replay = context.migration.finalize_run(
        context.operator,
        request,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )
    assert replay == result
    assert _semantic_counts(context.database) == before
    assert (
        context.store.resolve_importer(
            hashlib.sha256(context.credential.encode()).digest(),
            context.run.run_id,
            context.run.cutover_id,
            "ctower",
            datetime.now(UTC),
        )
        is None
    )
    refused_auth = context.access.authenticate_importer(
        f"Bearer {context.credential}",
        run_id=context.run.run_id,
        cutover_id=context.run.cutover_id,
        project_key="ctower",
    )
    assert isinstance(refused_auth, RecordProblem)
    finalized_batch = next_batch.model_copy(update={"batch_index": 4})
    assert isinstance(
        context.migration.apply_batch(
            context.importer,
            finalized_batch,
            telemetry=_telemetry(context.importer),
        ),
        RecordProblem,
    )


def _create_operator_ticket(database: _Database, operator: Actor) -> UUID:
    work = Work(PostgresRecord(database.runtime_dsn))
    command = TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=database.commander_id,
        priority="P2",
        source=SourceReference("synthetic", "synthetic:alias-target"),
        title="Existing exact alias target",
    )
    outcome = work.create_ticket(operator, command, telemetry=_telemetry(operator))
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


class _NoGeneralCredential:
    def actor_for_credential(self, credential_digest: bytes) -> None:
        del credential_digest


def _assert_database_event_guard(database: _Database, importer: Actor) -> None:
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        psycopg.connect(database.admin_dsn) as connection,
    ):
        connection.execute(
            """
            INSERT INTO events (
                event_id, tenant_id, stream_id, aggregate_id, sequence, kind,
                schema_version, actor_principal_id, client_command_id,
                request_sha256, correlation_id, origin, server_time, payload,
                prev_hash, event_hash, record_position
            ) VALUES (%s, %s, %s, %s, 1, 'proof.changed', 1, %s, %s,
                %s, %s, 'migration_importer', %s, %s, %s, %s, 999999)
            """,
            (
                uuid4(),
                database.tenant_id,
                f"proof:{uuid4()}",
                uuid4(),
                importer.principal_id,
                uuid4(),
                bytes(32),
                uuid4(),
                datetime.now(UTC),
                Jsonb({}),
                bytes(32),
                bytes.fromhex("01" * 32),
            ),
        )


def _assert_run_is_immutable(database: _Database, run_id: UUID) -> None:
    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        psycopg.connect(database.admin_dsn) as connection,
    ):
        connection.execute(
            "UPDATE migration_import_runs SET project_key = 'ctower' WHERE run_id = %s",
            (run_id,),
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
