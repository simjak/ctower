from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from ctower_client.models import (
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportRun,
    MigrationImportCounts,
    MigrationImporterBinding,
    MigrationImportOperationResult,
    MigrationPinnedDigests,
    ProjectDeliveryCriteria,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    sha256_digest,
)
from tools.migration.ctower_project.ctower_project_source.executor import (
    DryRunReceipt,
    ImportPassReceipt,
    execute_import,
    prove_pass_two,
)
from tools.migration.ctower_project.ctower_project_source.exporter import (
    FrozenExport,
    compare_exports,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    ImportPlan,
    build_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.reconcile import reconcile
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.source import ReadOnlySourceRoot

from .fixtures import (
    COMMANDER_ID,
    CUTOVER_ID,
    REVIEW,
    RUN_ID,
    UUID_NAMESPACE,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()

NOW = datetime(2026, 7, 25, 15, 45, tzinfo=UTC)
REQUEST_COUNT = 86
REQUEST_PHYSICAL_COUNT = 243


class FakeGeneratedClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, UUID]] = []
        self.responses: dict[UUID, CtowerProjectImportBatchResult] = {}
        self.fail_on_batch: int | None = None
        self.run: CtowerProjectImportRun | None = None
        self.delivery: ProjectDeliveryView | None = None

    def apply_ctower_project_import_batch(
        self,
        request: CtowerProjectImportBatchRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportBatchResult:
        if self.fail_on_batch == request.batch_index:
            raise RuntimeError("synthetic crash")
        self.calls.append((request.batch_index, command_id))
        previous = self.responses.get(command_id)
        if previous is not None:
            return previous.model_copy(
                update={
                    "results": tuple(
                        result.model_copy(update={"replayed": True}) for result in previous.results
                    )
                }
            )
        start = request.batch_index * 64
        results = tuple(
            MigrationImportOperationResult(
                command_id=operation.identity.command_id,
                operation_kind=operation.operation,
                replayed=False,
                target_id=f"target:{operation.identity.command_id}",
                event_ids=(uuid5(UUID_NAMESPACE, f"event:{operation.identity.command_id}"),),
                record_position=start + offset + 1,
                occurred_at=NOW,
            )
            for offset, operation in enumerate(request.operations)
        )
        response = CtowerProjectImportBatchResult(
            run_id=request.run_id,
            batch_index=request.batch_index,
            batch_digest=request.batch_digest,
            results=results,
            record_watermark=max(item.record_position for item in results),
            projection_watermark=0,
            durability_state="durability_pending",
            accepted_position=None,
        )
        self.responses[command_id] = response
        return response

    def get_ctower_project_import_run(self, run_id: UUID) -> CtowerProjectImportRun:
        assert self.run is not None and self.run.run_id == run_id
        return self.run

    def get_project_delivery(self, project_key: str) -> ProjectDeliveryView:
        assert self.delivery is not None and project_key == "ctower"
        return self.delivery


def _frozen_pair(
    fixture: SyntheticFixture,
) -> tuple[FrozenExport, dict[str, Any], dict[str, Any], ImportPlan]:
    root = ReadOnlySourceRoot(fixture.root)
    first = freeze_export(
        fixture.selection,
        root,
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_a",
        verifier=fixture.verifier,
    )
    second = freeze_export(
        fixture.selection,
        root,
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_b",
        verifier=fixture.verifier,
    )
    equality = compare_exports(first, second, review=REVIEW, signer=fixture.signer)
    alias_map = fixture.alias_map(equality)
    plan = build_import_plan(
        first,
        equality,
        alias_map,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=fixture.verifier,
    )
    return first, equality, alias_map, plan


def test_deterministic_64_item_plan_default_dry_run_and_exact_replay(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    _, _, _, plan = _frozen_pair(fixture)
    repeated = _frozen_pair(fixture)[3]
    assert [len(batch.operations) for batch in plan.batches] == [64, 7]
    assert canonical_bytes(
        [batch.model_dump(mode="json", by_alias=True) for batch in plan.batches]
    ) == canonical_bytes(
        [batch.model_dump(mode="json", by_alias=True) for batch in repeated.batches]
    )
    client = FakeGeneratedClient()
    dry = execute_import(plan, client=client)
    assert isinstance(dry, DryRunReceipt)
    assert not dry.applied
    assert client.calls == []
    first = execute_import(plan, client=client, apply=True)
    second = execute_import(plan, client=client, apply=True)
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    prove_pass_two(first, second)
    assert [index for index, _ in client.calls] == [0, 1, 0, 1]
    assert client.calls[0][1] == client.calls[2][1]
    assert client.calls[1][1] == client.calls[3][1]


def test_crash_resume_starts_at_first_unrecorded_contiguous_batch(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    plan = _frozen_pair(fixture)[3]
    client = FakeGeneratedClient()
    client.fail_on_batch = 1
    completed: list[CtowerProjectImportBatchResult] = []
    with pytest.raises(RuntimeError, match="synthetic crash"):
        execute_import(
            plan,
            client=client,
            apply=True,
            progress=completed.append,
        )
    assert [item.batch_index for item in completed] == [0]
    client.fail_on_batch = None
    receipt = execute_import(
        plan,
        client=client,
        apply=True,
        completed=tuple(completed),
    )
    assert isinstance(receipt, ImportPassReceipt)
    assert [index for index, _ in client.calls] == [0, 1]


def test_reconciliation_proves_frozen_equations_from_generated_reads(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    frozen, equality, alias_map, plan = _frozen_pair(fixture)
    client = FakeGeneratedClient()
    first = execute_import(plan, client=client, apply=True)
    second = execute_import(plan, client=client, apply=True)
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    client.run = _run(fixture, frozen, plan)
    client.delivery = _delivery(fixture, client.run)
    report = reconcile(
        frozen,
        equality,
        alias_map,
        plan,
        first,
        second,
        client=client,
        review=REVIEW,
        signer=fixture.signer,
    )
    assert report["conservation"]["selected_logical_items"] == REQUEST_COUNT
    assert report["conservation"]["selected_request_physical_snapshots"] == REQUEST_PHYSICAL_COUNT
    assert report["dispositions"] == {
        "created_ticket": 40,
        "alias_linked_existing": 20,
        "project_checkpoint_definition": 14,
        "decision_link": 5,
        "external_effect_link": 1,
        "artifact_linked_not_proof": 1,
        "provenance_only": 3,
        "exact_duplicate": 1,
        "excluded_out_of_scope": 1,
        "attention_required": 0,
    }
    assert fixture.verifier.verify(report, "report_digest") == report["report_digest"]


def test_changed_pass_two_response_and_unknown_target_refuse(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    frozen, equality, alias_map, plan = _frozen_pair(fixture)
    client = FakeGeneratedClient()
    first = execute_import(plan, client=client, apply=True)
    second = execute_import(plan, client=client, apply=True)
    assert isinstance(first, ImportPassReceipt)
    assert isinstance(second, ImportPassReceipt)
    changed_result = second.batches[0].results[0].model_copy(update={"target_id": "changed"})
    changed_batch = second.batches[0].model_copy(
        update={"results": (changed_result, *second.batches[0].results[1:])}
    )
    changed = ImportPassReceipt(
        second.run_id,
        second.cutover_id,
        (changed_batch, *second.batches[1:]),
    )
    with pytest.raises(MigrationRefusal) as caught:
        prove_pass_two(first, changed)
    assert caught.value.code == RefusalCode.IMPORT_REPLAY_DRIFT
    client.run = _run(fixture, frozen, plan).model_copy(update={"state": "importing"})
    client.delivery = _delivery(fixture, client.run)
    with pytest.raises(MigrationRefusal) as caught:
        reconcile(
            frozen,
            equality,
            alias_map,
            plan,
            first,
            second,
            client=client,
            review=REVIEW,
            signer=fixture.signer,
        )
    assert caught.value.code == RefusalCode.TARGET_STATE_UNKNOWN


def _run(
    fixture: SyntheticFixture, frozen: FrozenExport, plan: ImportPlan
) -> CtowerProjectImportRun:
    target = frozen.manifest["target_inventory"]
    return CtowerProjectImportRun(
        schema_id="ctower.ctower-project-import-run/v1",
        run_id=plan.run_id,
        cutover_id=plan.cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        state="pass_two_noop",
        pinned_digests=MigrationPinnedDigests(
            source_selection=plan.selection_digest,
            export_equality=plan.equality_digest,
            alias_map=plan.alias_map_digest,
            build=target["build_digest"],
            client=target["client_digest"],
            schema_id=target["schema_digest"],
            operation_registry=target["operation_registry_digest"],
            reviewer_public_key=fixture.verifier.public_key_digest,
        ),
        importer_binding=MigrationImporterBinding(
            principal_kind="migration_importer",
            credential_digest=sha256_digest(b"credential reference"),
            expires_at=NOW + timedelta(hours=1),
            revoked=False,
        ),
        counts=MigrationImportCounts(
            planned_operations=plan.operation_count,
            applied_operations=plan.operation_count,
            replayed_operations=plan.operation_count,
            refused_operations=0,
        ),
        record_watermark=plan.operation_count,
        projection_watermark=plan.operation_count,
        refusals=(),
        semantic_digest=sha256_digest(b"synthetic target facts"),
        durability_state="durability_pending",
        accepted_position=None,
    )


def _delivery(fixture: SyntheticFixture, run: CtowerProjectImportRun) -> ProjectDeliveryView:
    rows = tuple(
        ProjectDeliveryRow(
            checkpoint_key=key,
            checkpoint_label=f"Checkpoint {key}",
            headline_state="planned",
            underlying_maturity="planned",
            outcome=f"Reviewed outcome {key}",
            accountable_owner="ctower-engineering",
            criteria=ProjectDeliveryCriteria(proven=0, declared=1),
            source_watermark=run.record_watermark,
            projection_watermark=run.projection_watermark,
            freshness="fresh",
            confidence="development_degraded",
            health="CURRENT",
            durability="CP3_D_NOT_PROVEN",
            recovery="EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
            data_class="RECONSTRUCTIBLE_ONLY",
            semantic_digest=sha256_digest(key.encode()),
            reconciled_at=NOW,
            freshness_due_at=NOW + timedelta(minutes=15),
            rebuild_generation=0,
            source_ids=(f"catalog:ctower:checkpoint:{key}",),
            derivation_reasons=("synthetic reviewed checkpoint",),
        )
        for key in fixture.checkpoint_keys
    )
    return ProjectDeliveryView(
        schema_id="ctower.project-delivery/v1",
        company_key="ctower",
        project_key="ctower",
        source_record_position=run.record_watermark,
        projection_record_position=run.projection_watermark,
        reconciled_at=NOW,
        freshness_due_at=NOW + timedelta(minutes=15),
        projection_semantic_digest=sha256_digest(b"delivery"),
        rebuild_generation=0,
        rows=rows,
    )
