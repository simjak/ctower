"""Reconcile read-only generated-target results against frozen equations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

from ctower_client.models import (
    CtowerProjectImportRun,
    CtowerProjectTicketRelationOperation,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)

from .canonical import canonical_bytes, canonical_digest, validate_contract
from .executor import ImportPassReceipt, prove_pass_two
from .exporter import FrozenExport
from .import_plan import ImportPlan, seal_import_plan
from .refusal import MigrationRefusal, RefusalCode
from .signing import ArtifactSigner

__all__ = ("GeneratedTargetReader", "reconcile")

_RECONCILIATION_NAMESPACE = UUID("b77dc3f6-09c3-5f65-9616-2d6ee8b5287e")


class GeneratedTargetReader(Protocol):
    def get_ctower_project_import_run(self, run_id: UUID) -> CtowerProjectImportRun: ...

    def get_project_delivery(self, project_key: str) -> ProjectDeliveryView: ...


def reconcile(
    frozen: FrozenExport,
    equality: Mapping[str, Any],
    alias_map: Mapping[str, Any],
    plan: ImportPlan,
    pass_one: ImportPassReceipt,
    pass_two: ImportPassReceipt,
    *,
    client: GeneratedTargetReader,
    review: Mapping[str, Any],
    signer: ArtifactSigner,
) -> dict[str, Any]:
    prove_pass_two(pass_one, pass_two)
    if (
        equality.get("report_digest") != plan.equality_digest
        or alias_map.get("map_digest") != plan.alias_map_digest
    ):
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "artifact binding")
    run = client.get_ctower_project_import_run(plan.run_id)
    delivery = client.get_project_delivery("ctower")
    signed_plan = seal_import_plan(plan, frozen, review=review, signer=signer)
    _verify_target(
        run,
        delivery,
        frozen,
        plan,
        import_plan_digest=cast(str, signed_plan["plan_digest"]),
    )
    entries = cast(list[dict[str, Any]], alias_map["entries"])
    _verify_alias_conservation(frozen, entries)
    _verify_relations(plan)
    artifact = _report_payload(plan, run, signed_plan, review)
    sealed = signer.seal(artifact, "report_digest")
    validate_contract("ctower-project-reconciliation-v2.schema.json", sealed)
    return sealed


def _report_payload(
    plan: ImportPlan,
    run: CtowerProjectImportRun,
    signed_plan: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    if run.reconciliation_graph is None or run.pass_two_measurement is None:
        raise MigrationRefusal(RefusalCode.TARGET_STATE_UNKNOWN, "server reconciliation graph")
    actual_graph = run.reconciliation_graph.model_dump(mode="json")
    artifact: dict[str, Any] = {
        "schema": "ctower.ctower-project-reconciliation/v2",
        "reconciliation_id": str(
            uuid5(
                _RECONCILIATION_NAMESPACE,
                f"{plan.run_id}:{plan.cutover_id}:{run.semantic_digest}",
            )
        ),
        "run_id": str(plan.run_id),
        "cutover_id": str(plan.cutover_id),
        "project_key": "ctower",
        "pinned_digests": run.pinned_digests.model_dump(mode="json", by_alias=True),
        "reviewer_key": run.reviewer_key.model_dump(mode="json"),
        "expected_graph": _expected_graph(actual_graph, signed_plan),
        "actual_graph": actual_graph,
        "pass_two_measurement": run.pass_two_measurement.model_dump(mode="json"),
        "watermarks": {
            "source_native": run.source_native_watermark,
            "export_native": run.export_native_watermark,
            "record_position": run.record_watermark,
            "projection_position": run.projection_watermark,
        },
        "target_semantic_digest": run.semantic_digest,
        "reconciled_at": review["reviewed_at"],
        "review": dict(review),
        "durability_state": "durability_pending",
        "accepted_position": None,
    }
    return artifact


def _expected_graph(
    measured: dict[str, Any],
    signed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    definitions = cast(list[dict[str, str]], signed_plan["checkpoint_definitions"])
    expected = {
        **measured,
        "checkpoint_definitions": sorted(
            canonical_bytes(
                {
                    "checkpoint_key": item["checkpoint_key"],
                    "catalog_revision": item["catalog_revision"],
                    "definition_digest": item["definition_digest"],
                }
            ).decode()
            for item in definitions
        ),
        "checkpoint_criteria": sorted(
            canonical_bytes(
                {
                    "checkpoint_key": item["checkpoint_key"],
                    "criteria_digest": item["criteria_digest"],
                }
            ).decode()
            for item in definitions
        ),
    }
    expected["graph_digest"] = canonical_digest(
        {key: value for key, value in expected.items() if key != "graph_digest"}
    )
    return expected


def _verify_target(
    run: CtowerProjectImportRun,
    delivery: ProjectDeliveryView,
    frozen: FrozenExport,
    plan: ImportPlan,
    *,
    import_plan_digest: str,
) -> None:
    _verify_run_scope(run, plan)
    pinned = run.pinned_digests.model_dump(mode="json", by_alias=True)
    pinned.pop("reviewer_public_key", None)
    fence_registry = pinned.pop("fence_registry", None)
    if fence_registry is None:
        raise MigrationRefusal(
            RefusalCode.RECONCILIATION_MISMATCH,
            "verified fence registry pin",
        )
    if pinned != _expected_pins(frozen, plan, import_plan_digest=import_plan_digest):
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "pinned target digests")
    _verify_import_counts(run, plan)
    _verify_delivery(delivery, run, frozen)


def _verify_run_scope(run: CtowerProjectImportRun, plan: ImportPlan) -> None:
    if (
        run.run_id != plan.run_id
        or run.cutover_id != plan.cutover_id
        or run.project_key != "ctower"
        or run.tenant_key != "ctower"
    ):
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "target run tuple")
    if run.state != "pass_two_noop":
        code = (
            RefusalCode.TARGET_STATE_UNKNOWN
            if run.state not in {"pass_two_noop", "reconciled"}
            else RefusalCode.RECONCILIATION_MISMATCH
        )
        raise MigrationRefusal(code, "target import run state")


def _expected_pins(
    frozen: FrozenExport,
    plan: ImportPlan,
    *,
    import_plan_digest: str,
) -> dict[str, Any]:
    return {
        "source_selection": plan.selection_digest,
        "export_equality": plan.equality_digest,
        "alias_map": plan.alias_map_digest,
        "import_plan": import_plan_digest,
        "build": frozen.manifest["target_inventory"]["build_digest"],
        "client": frozen.manifest["target_inventory"]["client_digest"],
        "schema": frozen.manifest["target_inventory"]["schema_digest"],
        "operation_registry": frozen.manifest["target_inventory"]["operation_registry_digest"],
    }


def _verify_import_counts(run: CtowerProjectImportRun, plan: ImportPlan) -> None:
    if (
        run.counts.planned_operations != plan.operation_count
        or run.counts.applied_operations != plan.operation_count
        or run.counts.replayed_operations != plan.operation_count
        or run.counts.refused_operations != 0
        or run.refusals
    ):
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "target import counts")


def _verify_delivery(
    delivery: ProjectDeliveryView,
    run: CtowerProjectImportRun,
    frozen: FrozenExport,
) -> None:
    expected_checkpoint_keys = {
        record.identity.immutable_source_id
        for record in frozen.records
        if record.identity.namespace == "catalog:ctower:checkpoint"
    }
    invalid_scope = (
        delivery.company_key != "ctower"
        or delivery.project_key != "ctower"
        or len(delivery.rows) != len(expected_checkpoint_keys)
        or delivery.source_record_position < run.record_watermark
        or delivery.projection_record_position < run.projection_watermark
    )
    if invalid_scope:
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "project delivery")
    keys = {row.checkpoint_key for row in delivery.rows}
    if keys != expected_checkpoint_keys:
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "checkpoint definitions")
    for row in delivery.rows:
        _verify_delivery_row(row)


def _verify_delivery_row(row: ProjectDeliveryRow) -> None:
    states = (
        row.freshness,
        row.confidence,
        row.health,
        row.durability,
        row.recovery,
        row.data_class,
    )
    if "STATE_UNKNOWN" in states:
        raise MigrationRefusal(RefusalCode.TARGET_STATE_UNKNOWN, "project delivery row")
    if not row.accountable_owner or row.criteria.declared < 1:
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "owner or criteria")


def _verify_alias_conservation(frozen: FrozenExport, entries: list[dict[str, Any]]) -> None:
    exported = {_record_key(record.identity.model_dump(mode="json")) for record in frozen.records}
    mapped = {_record_key(cast(dict[str, Any], entry["identity"])) for entry in entries}
    if not mapped.issubset(exported) or len(mapped) != len(entries):
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "identity conservation")
    requests = {key for key in exported if key[0] == "mission-control:request"}
    # Every exported request identity must have exactly one alias-map entry.
    # requests != mapped (set equality) covers both cardinality and identity.
    if requests != mapped:
        raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "request identity coverage")


def _verify_relations(plan: ImportPlan) -> None:
    _reject_relation_cycles(_relation_edges(plan))


def _relation_edges(plan: ImportPlan) -> dict[UUID, set[UUID]]:
    edges: dict[UUID, set[UUID]] = defaultdict(set)
    for batch in plan.batches:
        for operation in batch.operations:
            if isinstance(operation, CtowerProjectTicketRelationOperation):
                if operation.source_ticket_id == operation.target_ticket_id:
                    raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "self relation")
                if operation.relation_kind in {"parent_of", "depends_on", "blocks"}:
                    edges[operation.source_ticket_id].add(operation.target_ticket_id)
    return edges


def _reject_relation_cycles(edges: Mapping[UUID, set[UUID]]) -> None:
    visiting: set[UUID] = set()
    visited: set[UUID] = set()

    def visit(node: UUID) -> None:
        if node in visiting:
            raise MigrationRefusal(RefusalCode.RECONCILIATION_MISMATCH, "forbidden relation cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in edges[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in tuple(edges):
        visit(node)


def _record_key(identity: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(identity["namespace"]),
        str(identity["immutable_source_id"]),
        str(identity["source_version"]),
    )
