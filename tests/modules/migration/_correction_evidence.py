"""Append-only migration correction evidence shared by PostgreSQL tests."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID, uuid4

from ctower_client.models import (
    CtowerProjectImportBatchResult,
    CtowerProjectImportCorrectionRequest,
    CtowerProjectImportRun,
    MigrationAliasCorrection,
    MigrationCorrectionRevision,
    MigrationSourceLinkCorrection,
)
from ctower_kernel.migration import Migration
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from tools.migration.ctower_project.ctower_project_source.import_plan import ImportPlan

from ._postgres import Database, alias_digest, semantic_counts, source_link_digest

__all__ = ["assert_append_only_corrections"]


class _RunContext(Protocol):
    @property
    def migration(self) -> Migration: ...

    @property
    def operator(self) -> Actor: ...

    @property
    def created(self) -> CtowerProjectImportRun: ...


def assert_append_only_corrections(
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
    _assert_alias_correction(context, database, target_id, alias.identity.command_id)
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
