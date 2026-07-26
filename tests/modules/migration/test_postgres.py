"""Real PostgreSQL proof for the reviewed migration truth spine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectReconciliationResult,
    MigrationAliasCorrection,
    MigrationCorrectionRevision,
    MigrationSourceLinkCorrection,
)
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    execute_import,
    prove_pass_two,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import ImportPlan

from ._postgres import Database, alias_digest, semantic_counts, source_link_digest
from ._reviewed import ReviewedSource, reviewed_source
from .source_tool.fixtures import CUTOVER_ID

_OPERATION_COUNT = 71
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
    _assert_append_only_corrections(context, migration_database, plan, first_batch)
    first = execute_import(
        plan,
        client=_MigrationClient(context.migration, importer),
        apply=True,
        completed=(first_batch,),
    )
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
    result = context.migration.finalize_run(
        context.operator,
        _finalize(ready),
        command_id=uuid4(),
        telemetry=_telemetry(context.operator),
    )
    _assert_finalized(
        result,
        ready,
        context.store,
        context.credential_digest,
        context.now,
    )


def _start_run(database: Database, tmp_path: Path) -> _RunContext:
    now = datetime.now(UTC)
    source = reviewed_source(tmp_path, CUTOVER_ID)
    store = PostgresMigration(
        database.runtime_dsn,
        trusted_reviewer_keys=source.trusted_keys,
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
    )


def _bind_reviewed_plan(
    context: _RunContext,
    database: Database,
) -> tuple[Actor, ImportPlan]:
    _assert_export_graph_refusals(context, database)
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
    _assert_plan_graph_refusals(context, database, plan_request)
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


def _assert_export_graph_refusals(context: _RunContext, database: Database) -> None:
    request = context.source.export_request(context.created.run_id)
    malformed = request.model_copy(
        update={"export_equality_artifact": canonical_bytes({"invalid": True}).decode()}
    )
    export_a = json.loads(request.export_a_artifact)
    export_a["artifact_digest"] = f"sha256:{'0' * 64}"
    bad_export_digest = request.model_copy(
        update={"export_a_artifact": canonical_bytes(export_a).decode()}
    )
    equality = _reseal(
        context,
        request.export_equality_artifact,
        "report_digest",
        {"cutover_id": str(uuid4())},
    )
    rebound = request.model_copy(
        update={
            "equality_report_digest": equality["report_digest"],
            "export_equality_artifact": canonical_bytes(equality).decode(),
        }
    )
    bad_inventory = request.model_copy(update={"inventory_a_digest": f"sha256:{'0' * 64}"})
    for candidate in (malformed, bad_export_digest, rebound, bad_inventory):
        before = semantic_counts(database)
        refused = context.migration.bind_export_equality(
            context.operator,
            candidate,
            command_id=uuid4(),
            telemetry=_telemetry(context.operator),
        )
        assert isinstance(refused, RecordProblem)
        assert semantic_counts(database) == before


def _assert_plan_graph_refusals(
    context: _RunContext,
    database: Database,
    plan_request: CtowerProjectAliasPlanBindRequest,
) -> None:
    plan_nonexhaustive = json.loads(plan_request.import_plan_artifact)
    plan_nonexhaustive["operation_count"] += 1
    plan_batch = json.loads(plan_request.import_plan_artifact)
    plan_batch["batches"][0]["batch_index"] = 9
    plan_command = json.loads(plan_request.import_plan_artifact)
    plan_command["batches"][0]["operations"][0]["identity"]["command_id"] = str(uuid4())
    batch = plan_command["batches"][0]
    batch["batch_digest"] = canonical_digest(
        {key: value for key, value in batch.items() if key != "batch_digest"}
    )
    candidates = (
        plan_request.model_copy(update={"alias_map_digest": f"sha256:{'0' * 64}"}),
        _plan_candidate(context, plan_request, plan_nonexhaustive),
        _plan_candidate(context, plan_request, plan_batch),
        _plan_candidate(context, plan_request, plan_command),
        _artifact_candidate(
            context,
            plan_request,
            "alias_map_artifact",
            "map_digest",
            {"attention_required": 1},
        ),
        _artifact_candidate(
            context,
            plan_request,
            "fence_registry_artifact",
            "registry_digest",
            {"cutover_id": str(uuid4())},
        ),
    )
    for candidate in candidates:
        before = semantic_counts(database)
        refused = context.migration.bind_alias_plan(
            context.operator,
            candidate,
            command_id=uuid4(),
            telemetry=_telemetry(context.operator),
        )
        assert isinstance(refused, RecordProblem)
        assert semantic_counts(database) == before


def _plan_candidate(
    context: _RunContext,
    request: CtowerProjectAliasPlanBindRequest,
    plan: dict[str, object],
) -> CtowerProjectAliasPlanBindRequest:
    unsigned = {
        key: value for key, value in plan.items() if key not in {"plan_digest", "signature"}
    }
    sealed = context.source.fixture.signer.seal(unsigned, "plan_digest")
    return request.model_copy(update={"import_plan_artifact": canonical_bytes(sealed).decode()})


def _artifact_candidate(
    context: _RunContext,
    request: CtowerProjectAliasPlanBindRequest,
    field: Literal["alias_map_artifact", "fence_registry_artifact"],
    digest_field: Literal["map_digest", "registry_digest"],
    update: dict[str, object],
) -> CtowerProjectAliasPlanBindRequest:
    artifact = getattr(request, field)
    sealed = _reseal(context, artifact, digest_field, update)
    return request.model_copy(update={field: canonical_bytes(sealed).decode()})


def _reseal(
    context: _RunContext,
    artifact_text: str,
    digest_field: Literal["report_digest", "map_digest", "registry_digest"],
    update: dict[str, object],
) -> dict[str, object]:
    artifact = json.loads(artifact_text)
    unsigned = {
        key: value for key, value in artifact.items() if key not in {digest_field, "signature"}
    }
    unsigned.update(update)
    return context.source.fixture.signer.seal(unsigned, digest_field)


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


def _assert_append_only_corrections(
    context: _RunContext,
    database: Database,
    plan: ImportPlan,
    first_batch: CtowerProjectImportBatchResult,
) -> None:
    target_id = UUID(first_batch.results[0].target_id)
    alias = next(item for item in plan.batches[0].operations if item.operation == "exact_alias")
    source_link = next(
        item for item in plan.batches[0].operations if item.operation == "source_link"
    )
    _assert_alias_correction(
        context,
        database,
        target_id,
        alias.identity.command_id,
    )
    _assert_source_link_correction(
        context,
        database,
        target_id,
        source_link.identity.command_id,
    )


def _assert_alias_correction(
    context: _RunContext,
    database: Database,
    target_id: UUID,
    alias_id: UUID,
) -> None:
    request = _correction(
        context,
        "alias",
        alias_id,
        alias_digest(database, alias_id),
        MigrationAliasCorrection(
            kind="alias",
            target_ticket_id=uuid4(),
            disposition="provenance_only",
        ),
    )
    before = semantic_counts(database)
    refused = _append(context, request, uuid4())
    assert isinstance(refused, RecordProblem)
    assert semantic_counts(database) == before
    accepted = request.model_copy(
        update={
            "correction_id": uuid4(),
            "replacement": request.replacement.model_copy(update={"target_ticket_id": target_id}),
        }
    )
    _assert_correction_replay_and_stale(context, database, accepted)


def _assert_source_link_correction(
    context: _RunContext,
    database: Database,
    target_id: UUID,
    link_id: UUID,
) -> None:
    request = _correction(
        context,
        "source_link",
        link_id,
        source_link_digest(database, link_id),
        MigrationSourceLinkCorrection(
            kind="source_link",
            target_kind="ticket",
            target_id=f"ticket:{uuid4()}",
            disposition="provenance_only",
        ),
    )
    before = semantic_counts(database)
    refused = _append(context, request, uuid4())
    assert isinstance(refused, RecordProblem)
    assert semantic_counts(database) == before
    accepted = request.model_copy(
        update={
            "correction_id": uuid4(),
            "replacement": request.replacement.model_copy(
                update={"target_id": f"ticket:{target_id}"}
            ),
        }
    )
    _assert_correction_replay_and_stale(context, database, accepted)


def _correction(
    context: _RunContext,
    kind: Literal["alias", "source_link"],
    object_id: UUID,
    expected_digest: str,
    replacement: MigrationAliasCorrection | MigrationSourceLinkCorrection,
) -> CtowerProjectImportCorrectionRequest:
    return CtowerProjectImportCorrectionRequest(
        schema_id="ctower.ctower-project-import-correction/v1",
        correction_id=uuid4(),
        run_id=context.created.run_id,
        cutover_id=context.created.cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        correction_kind=kind,
        superseded_revision=MigrationCorrectionRevision(object_id=object_id, revision=1),
        expected_current_digest=expected_digest,
        replacement=replacement,
        reason="Reviewed append-only correction",
        reviewer_id=context.operator.principal_id,
    )


def _append(
    context: _RunContext,
    request: CtowerProjectImportCorrectionRequest,
    command_id: UUID,
) -> object:
    return context.migration.append_correction(
        context.operator,
        request,
        command_id=command_id,
        telemetry=_telemetry(context.operator),
    )


def _assert_correction_replay_and_stale(
    context: _RunContext,
    database: Database,
    request: CtowerProjectImportCorrectionRequest,
) -> None:
    command_id = uuid4()
    receipt = _append(context, request, command_id)
    assert not isinstance(receipt, RecordProblem)
    before = semantic_counts(database)
    assert _append(context, request, command_id) == receipt
    drift = request.model_copy(update={"reason": "Changed replay"})
    drifted = _append(context, drift, command_id)
    assert isinstance(drifted, RecordProblem)
    assert drifted.code == "migration-operation-drift"
    stale = request.model_copy(update={"correction_id": uuid4()})
    refused = _append(context, stale, uuid4())
    assert isinstance(refused, RecordProblem)
    assert refused.code == "migration-correction-conflict"
    assert semantic_counts(database) == before


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


def _assert_finalized(
    result: object,
    ready: CtowerProjectImportRun,
    store: PostgresMigration,
    credential_digest: bytes,
    now: datetime,
) -> None:
    assert not isinstance(result, RecordProblem)
    assert isinstance(result, CtowerProjectReconciliationResult)
    assert result.conservation == ready.conservation
    assert store.resolve_importer_credential(credential_digest, now) is None


def _create_target(database: Database, operator: Actor) -> UUID:
    outcome = Work(PostgresRecord(database.runtime_dsn)).create_ticket(
        operator,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=database.commander_id,
            priority="P2",
            source=SourceReference("synthetic", "synthetic:alias-target"),
            title="Existing exact alias target",
        ),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _finalize(run: CtowerProjectImportRun) -> CtowerProjectImportFinalizeRequest:
    return CtowerProjectImportFinalizeRequest(
        run_id=run.run_id,
        cutover_id=run.cutover_id,
        expected_run_semantic_digest=run.semantic_digest,
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
