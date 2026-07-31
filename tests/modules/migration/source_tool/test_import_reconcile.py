from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from ctower_client.models import (
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
    CtowerProjectImportRun,
    DurabilityState,
    MigrationConservation,
    MigrationDispositions,
    MigrationImportCounts,
    MigrationImporterBinding,
    MigrationImportOperationResult,
    MigrationPassTwoMeasurement,
    MigrationPinnedDigests,
    MigrationReconciliationGraph,
    MigrationReviewerKey,
    ProjectDeliveryCriteria,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
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
    seal_import_plan,
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
    DISPOSITIONS,
    REVIEW,
    RUN_ID,
    UUID_NAMESPACE,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()
_STABLE_COUNT = 27

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
            durability_state=DurabilityState.DURABILITY_PENDING,
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
    assert [len(batch.operations) for batch in plan.batches] == [64, 34]
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
    assert report["expected_graph"] == report["actual_graph"]
    assert len(report["actual_graph"]["stable_aliases"]) == _STABLE_COUNT
    assert len(report["actual_graph"]["checkpoint_definitions"]) == len(fixture.checkpoint_keys)
    assert report["pass_two_measurement"]["new_domain_facts"] == 0
    assert report["pass_two_measurement"]["new_events"] == 0
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
    signed_plan = seal_import_plan(
        plan,
        frozen,
        review=REVIEW,
        signer=fixture.signer,
    )
    return CtowerProjectImportRun(
        schema_id="ctower.ctower-project-import-run/v2",
        run_id=plan.run_id,
        cutover_id=plan.cutover_id,
        tenant_key="ctower",
        project_key="ctower",
        state="pass_two_noop",
        pinned_digests=MigrationPinnedDigests(
            source_selection=plan.selection_digest,
            export_equality=plan.equality_digest,
            alias_map=plan.alias_map_digest,
            import_plan=signed_plan["plan_digest"],
            fence_registry=sha256_digest(b"fence registry"),
            build=target["build_digest"],
            client=target["client_digest"],
            schema_id=target["schema_digest"],
            operation_registry=target["operation_registry_digest"],
            reviewer_public_key=fixture.verifier.public_key_digest,
        ),
        reviewer_key=MigrationReviewerKey(
            public_key_ref="signing-key-ref:test/reviewer",
            key_version=1,
            public_key_digest=fixture.verifier.public_key_digest,
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
        dispositions=MigrationDispositions(
            **Counter(DISPOSITIONS),
            attention_required=0,
        ),
        conservation=_conservation(),
        reconciliation_graph=_graph(fixture, signed_plan),
        pass_two_measurement=_pass_two(),
        source_native_watermark=243,
        export_native_watermark=243,
        record_watermark=plan.operation_count,
        projection_watermark=plan.operation_count,
        refusals=(),
        semantic_digest=sha256_digest(b"synthetic target facts"),
        durability_state=DurabilityState.DURABILITY_PENDING,
        accepted_position=None,
    )


def _graph(
    fixture: SyntheticFixture,
    signed_plan: dict[str, Any],
) -> MigrationReconciliationGraph:
    definitions = signed_plan["checkpoint_definitions"]
    value: dict[str, Any] = {
        "stable_aliases": tuple(f"stable:{item}" for item in fixture.stable_ids),
        "operation_identities": (),
        "operation_results": (),
        "tickets": (),
        "lifecycle_facts": (),
        "priority_facts": (),
        "custody_intervals": (),
        "active_claims": (),
        "alias_revisions": (),
        "relations": (),
        "relation_endpoints": (),
        "source_links": (),
        "checkpoint_definitions": tuple(
            sorted(
                canonical_bytes(
                    {
                        "checkpoint_key": item["checkpoint_key"],
                        "catalog_revision": item["catalog_revision"],
                        "definition_digest": item["definition_digest"],
                    }
                ).decode()
                for item in definitions
            )
        ),
        "checkpoint_criteria": tuple(
            sorted(
                canonical_bytes(
                    {
                        "checkpoint_key": item["checkpoint_key"],
                        "criteria_digest": item["criteria_digest"],
                    }
                ).decode()
                for item in definitions
            )
        ),
        "project_delivery_rows": tuple(f"delivery:{item}" for item in fixture.checkpoint_keys),
        "events": (),
        "outbox_rows": (),
        "unexpected": (),
        "forbidden": (),
        "unresolved": (),
        "cycles": (),
    }
    value["graph_digest"] = canonical_digest(value)
    return MigrationReconciliationGraph.model_validate(value)


def _pass_two() -> MigrationPassTwoMeasurement:
    digest = sha256_digest(b"synthetic pass-two snapshot")
    delivery = sha256_digest(b"synthetic project delivery")
    return MigrationPassTwoMeasurement(
        start_snapshot_digest=digest,
        end_snapshot_digest=digest,
        start_domain_facts=0,
        end_domain_facts=0,
        new_domain_facts=0,
        start_events=0,
        end_events=0,
        new_events=0,
        start_outbox_rows=0,
        end_outbox_rows=0,
        new_outbox_rows=0,
        start_record_position=0,
        end_record_position=0,
        record_position_delta=0,
        start_project_delivery_digest=delivery,
        end_project_delivery_digest=delivery,
        projection_semantic_delta=0,
    )


def _conservation() -> MigrationConservation:
    return MigrationConservation(
        selected_logical_items=86,
        selected_request_logical=86,
        selected_request_physical_snapshots=243,
        stable_aliases=27,
        checkpoint_definitions=14,
        unresolved_aliases=0,
        alias_forks_or_cycles=0,
        missing_relation_endpoints=0,
        forbidden_relation_cycles=0,
        unresolved_active_claims=0,
        unexpected_sources=0,
        forbidden_data_items=0,
        pass_two_new_domain_facts=0,
        pass_two_new_events=0,
        pass_two_new_outbox_rows=0,
        pass_two_record_position_delta=0,
        pass_two_projection_semantic_delta=0,
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
            qualifying_stage_slots_filled=0,
            qualifying_stage_slots_required=1,
            qualifying_stage_unfilled_or_unknown_slot_keys=("declared-outcome",),
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
