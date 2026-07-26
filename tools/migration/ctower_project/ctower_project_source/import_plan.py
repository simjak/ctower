"""Plan only the four deterministic frozen generated-client operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid5

from ctower_client.models import (
    CtowerProjectExactAliasOperation,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportOperation,
    CtowerProjectSourceLinkOperation,
    CtowerProjectTicketRelationOperation,
    CtowerProjectTicketSeedOperation,
    MigrationOperationIdentity,
    MigrationSourceIdentity,
)

from .canonical import canonical_digest, validate_contract
from .exporter import FrozenExport
from .refusal import MigrationRefusal, RefusalCode
from .signing import ArtifactSigner, ArtifactVerifier
from .source import SourceIdentity, SourceRecord

__all__ = ("ImportPlan", "build_import_plan", "seal_import_plan")

_COMMAND_NAMESPACE = UUID("7c4ef338-17fd-5be3-a6b7-c89205ecb574")
_PLAN_NAMESPACE = UUID("60d52ae5-e001-5922-ae0c-6b5e4c7aa6fa")
_BATCH_SIZE = 64
_CONTROL_CHARACTER_LIMIT = 32
_DELETE_CHARACTER = 127


@dataclass(frozen=True)
class ImportPlan:
    run_id: UUID
    cutover_id: UUID
    selection_digest: str
    equality_digest: str
    alias_map_digest: str
    batches: tuple[CtowerProjectImportBatchRequest, ...]
    plan_digest: str

    @property
    def operation_count(self) -> int:
        return sum(len(batch.operations) for batch in self.batches)


def build_import_plan(
    frozen: FrozenExport,
    equality: Mapping[str, Any],
    alias_map: Mapping[str, Any],
    *,
    run_id: UUID,
    cutover_id: UUID,
    commander_custodian_id: UUID,
    verifier: ArtifactVerifier,
) -> ImportPlan:
    equality_digest = _verify_equality(equality, frozen, cutover_id, verifier)
    alias_digest = _verify_alias_map(
        alias_map,
        selection_digest=str(frozen.manifest["selection_digest"]),
        equality_digest=equality_digest,
        cutover_id=cutover_id,
        verifier=verifier,
    )
    records = _unique_records(frozen.records)
    operations: list[CtowerProjectImportOperation] = []
    entries = cast(list[dict[str, Any]], alias_map["entries"])
    operations.extend(_stable_alias_operations(alias_map, records))
    for entry in sorted(entries, key=_entry_key):
        source = _source_identity(entry["identity"])
        record = records.get(source.key())
        if record is None:
            raise MigrationRefusal(RefusalCode.ALIAS_OUTSIDE_EXPORT, "alias identity")
        primary = _primary_operation(entry, record, source, commander_custodian_id)
        if primary is not None:
            operations.append(primary)
        relation = _relation_operation(record, source)
        if relation is not None:
            operations.append(relation)
    operations.sort(key=_operation_key)
    batches = _batches(run_id, cutover_id, operations)
    plan_digest = canonical_digest(
        [batch.model_dump(mode="json", by_alias=True) for batch in batches]
    )
    return ImportPlan(
        run_id,
        cutover_id,
        str(frozen.manifest["selection_digest"]),
        equality_digest,
        alias_digest,
        batches,
        plan_digest,
    )


def _stable_alias_operations(
    alias_map: Mapping[str, Any],
    records: Mapping[tuple[str, str, str], SourceRecord],
) -> list[CtowerProjectImportOperation]:
    operations: list[CtowerProjectImportOperation] = []
    for mapping in cast(list[dict[str, Any]], alias_map["stable_aliases"]):
        stable_id = str(mapping["stable_item_id"])
        candidates = [
            record
            for key, record in records.items()
            if key[0] == "stable-backlog" and key[1] == stable_id
        ]
        if len(candidates) != 1:
            raise MigrationRefusal(
                RefusalCode.ALIAS_OUTSIDE_EXPORT,
                "stable alias identity",
            )
        record = candidates[0]
        target_ref = f"ticket:{mapping['target_ticket_id']}"
        operation = _primary_operation(
            {
                "disposition": "alias_linked_existing",
                "planned_target_ref": target_ref,
            },
            record,
            record.identity,
            UUID(int=0),
        )
        if operation is None:
            raise MigrationRefusal(
                RefusalCode.ALIAS_ATTENTION_REQUIRED,
                "stable alias operation",
            )
        operations.append(operation)
    return operations


def seal_import_plan(
    plan: ImportPlan,
    frozen: FrozenExport,
    *,
    review: Mapping[str, Any],
    signer: ArtifactSigner,
) -> dict[str, Any]:
    """Seal the exhaustive generated-client requests reviewed by the server."""

    sources = cast(list[dict[str, Any]], frozen.manifest["sources"])
    watermark = max(int(source["last_complete_offset"]) for source in sources)
    artifact: dict[str, Any] = {
        "schema": "ctower.ctower-project-import-plan/v2",
        "plan_id": str(uuid5(_PLAN_NAMESPACE, f"{plan.run_id}:{plan.cutover_id}")),
        "run_id": str(plan.run_id),
        "cutover_id": str(plan.cutover_id),
        "selection_digest": plan.selection_digest,
        "export_equality_digest": plan.equality_digest,
        "alias_map_digest": plan.alias_map_digest,
        "created_at": review["reviewed_at"],
        "batch_count": len(plan.batches),
        "operation_count": plan.operation_count,
        "batches": [batch.model_dump(mode="json", by_alias=True) for batch in plan.batches],
        "checkpoint_definitions": [
            {
                "checkpoint_key": record.identity.immutable_source_id,
                "catalog_revision": record.identity.source_version,
                "definition_digest": record.identity.source_digest,
                "criteria_digest": record.identity.source_digest,
            }
            for record in sorted(
                (
                    item
                    for item in frozen.records
                    if item.identity.namespace == "catalog:ctower:checkpoint"
                ),
                key=lambda item: item.identity.immutable_source_id,
            )
        ],
        "source_native_watermark": watermark,
        "export_native_watermark": watermark,
        "review": dict(review),
    }
    sealed = signer.seal(artifact, "plan_digest")
    validate_contract("ctower-project-import-plan-v2.schema.json", sealed)
    return sealed


def _verify_equality(
    equality: Mapping[str, Any],
    frozen: FrozenExport,
    cutover_id: UUID,
    verifier: ArtifactVerifier,
) -> str:
    validate_contract("ctower-project-export-equality.schema.json", equality)
    digest = verifier.verify(equality, "report_digest")
    if (
        equality.get("result") != "equal"
        or equality.get("cutover_id") != str(cutover_id)
        or equality.get("selection_digest") != frozen.manifest["selection_digest"]
        or frozen.manifest["artifact_digest"]
        not in {equality.get("export_a_digest"), equality.get("export_b_digest")}
    ):
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "export equality binding")
    return digest


def _verify_alias_map(
    alias_map: Mapping[str, Any],
    *,
    selection_digest: str,
    equality_digest: str,
    cutover_id: UUID,
    verifier: ArtifactVerifier,
) -> str:
    validate_contract("ctower-project-alias-map-v2.schema.json", alias_map)
    digest = verifier.verify(alias_map, "map_digest")
    if alias_map.get("attention_required") != 0 or any(
        item.get("disposition") == "attention_required"
        for item in cast(list[dict[str, Any]], alias_map["entries"])
    ):
        raise MigrationRefusal(RefusalCode.ALIAS_ATTENTION_REQUIRED, "reviewed alias map")
    if (
        alias_map.get("selection_digest") != selection_digest
        or alias_map.get("export_equality_digest") != equality_digest
        or alias_map.get("cutover_id") != str(cutover_id)
    ):
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "alias map binding")
    keys = [_entry_key(item) for item in cast(list[dict[str, Any]], alias_map["entries"])]
    if len(set(keys)) != len(keys):
        raise MigrationRefusal(RefusalCode.ALIAS_IDENTITY_DUPLICATE, "alias entries")
    return digest


def _unique_records(records: tuple[SourceRecord, ...]) -> dict[tuple[str, str, str], SourceRecord]:
    unique: dict[tuple[str, str, str], SourceRecord] = {}
    for record in records:
        key = record.identity.key()
        previous = unique.setdefault(key, record)
        if previous != record:
            raise MigrationRefusal(RefusalCode.SOURCE_DRIFT, "logical snapshot disagreement")
    return unique


def _primary_operation(
    entry: Mapping[str, Any],
    record: SourceRecord,
    source: SourceIdentity,
    commander_id: UUID,
) -> CtowerProjectImportOperation | None:
    disposition = str(entry["disposition"])
    target_ref = entry.get("planned_target_ref")
    generated_source = _generated_source(source)
    if disposition == "created_ticket":
        if target_ref != "new_ticket" or record.title is None:
            raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "ticket seed target")
        return CtowerProjectTicketSeedOperation(
            operation="ticket_seed",
            identity=_identity(source, "ticket_seed", "new_ticket"),
            project_key="ctower",
            priority="P2",
            title=_safe_title(record.title),
            source=generated_source,
            initial_commander_custodian_id=commander_id,
        )
    if disposition in {"alias_linked_existing", "exact_duplicate"}:
        ticket_id = _target_uuid(target_ref, "ticket")
        return CtowerProjectExactAliasOperation(
            operation="exact_alias",
            identity=_identity(source, "exact_alias", str(target_ref)),
            project_key="ctower",
            source=generated_source,
            target_ticket_id=ticket_id,
        )
    if disposition in {
        "decision_link",
        "external_effect_link",
        "artifact_linked_not_proof",
        "provenance_only",
    }:
        target_kind, target_id = _link_target(target_ref)
        link_class = {
            "decision_link": "decision",
            "external_effect_link": "external_effect",
            "artifact_linked_not_proof": "artifact_not_proof",
            "provenance_only": "provenance",
        }[disposition]
        return CtowerProjectSourceLinkOperation(
            operation="source_link",
            identity=_identity(source, "source_link", str(target_ref)),
            project_key="ctower",
            source=generated_source,
            link_class=cast(Any, link_class),
            target_kind=cast(Any, target_kind),
            target_id=target_id,
            reason_code=str(entry["reason_code"]),
            linked_not_proof=True,
        )
    if disposition in {
        "project_checkpoint_definition",
        "excluded_out_of_scope",
    }:
        return None
    raise MigrationRefusal(RefusalCode.ALIAS_ATTENTION_REQUIRED, "unknown disposition")


def _relation_operation(
    record: SourceRecord, source: SourceIdentity
) -> CtowerProjectTicketRelationOperation | None:
    hint = record.operation_hint
    if hint is None or hint.relation_kind is None:
        return None
    if not hint.source_ticket_id or not hint.relation_target_ticket_id or not hint.relation_reason:
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "relation hint")
    source_ticket = _parse_uuid(hint.source_ticket_id, "relation source")
    target_ticket = _parse_uuid(hint.relation_target_ticket_id, "relation target")
    relation_ref = f"relation:{hint.relation_kind}:{source_ticket}:{target_ticket}"
    relation_id = uuid5(_COMMAND_NAMESPACE, relation_ref)
    return CtowerProjectTicketRelationOperation(
        operation="ticket_relation",
        identity=_identity(source, "ticket_relation", relation_ref),
        project_key="ctower",
        relation_id=relation_id,
        relation_kind=hint.relation_kind,
        source_ticket_id=source_ticket,
        target_ticket_id=target_ticket,
        reason=hint.relation_reason,
    )


def _identity(
    source: SourceIdentity, operation_kind: str, planned_target_ref: str
) -> MigrationOperationIdentity:
    stable = (
        f"{source.namespace}|{source.immutable_source_id}|{source.source_version}|"
        f"{operation_kind}|{planned_target_ref}"
    )
    return MigrationOperationIdentity(
        namespace=source.namespace,
        immutable_source_id=source.immutable_source_id,
        source_version_or_digest=source.source_version,
        operation_kind=cast(Any, operation_kind),
        planned_target_ref=planned_target_ref,
        command_id=uuid5(_COMMAND_NAMESPACE, stable),
    )


def _batches(
    run_id: UUID,
    cutover_id: UUID,
    operations: list[CtowerProjectImportOperation],
) -> tuple[CtowerProjectImportBatchRequest, ...]:
    batches: list[CtowerProjectImportBatchRequest] = []
    for index, start in enumerate(range(0, len(operations), _BATCH_SIZE)):
        chunk = tuple(operations[start : start + _BATCH_SIZE])
        seed = {
            "schema": "ctower.ctower-project-import-batch/v1",
            "run_id": str(run_id),
            "cutover_id": str(cutover_id),
            "batch_index": index,
            "operations": [item.model_dump(mode="json", by_alias=True) for item in chunk],
        }
        batch = CtowerProjectImportBatchRequest(
            schema_id="ctower.ctower-project-import-batch/v1",
            run_id=run_id,
            cutover_id=cutover_id,
            batch_index=index,
            batch_digest=canonical_digest(seed),
            operations=chunk,
        )
        validate_contract(
            "ctower-project-import-batch.schema.json",
            batch.model_dump(mode="json", by_alias=True),
        )
        batches.append(batch)
    return tuple(batches)


def _generated_source(source: SourceIdentity) -> MigrationSourceIdentity:
    return MigrationSourceIdentity.model_validate(source.model_dump(mode="json"))


def _source_identity(value: object) -> SourceIdentity:
    return SourceIdentity.model_validate(value)


def _entry_key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    identity = cast(dict[str, str], entry["identity"])
    return identity["namespace"], identity["immutable_source_id"], identity["source_version"]


def _operation_key(operation: CtowerProjectImportOperation) -> tuple[str, ...]:
    identity = operation.identity
    return (
        identity.namespace,
        identity.immutable_source_id,
        identity.source_version_or_digest,
        identity.operation_kind,
        identity.planned_target_ref,
    )


def _target_uuid(value: object, kind: str) -> UUID:
    if not isinstance(value, str) or not value.startswith(f"{kind}:"):
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, f"{kind} target")
    return _parse_uuid(value.split(":", 1)[1], f"{kind} target")


def _parse_uuid(value: str, context: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, context) from error


def _link_target(value: object) -> tuple[str, str]:
    if not isinstance(value, str) or ":" not in value:
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "source link target")
    prefix, target_id = value.split(":", 1)
    kinds = {
        "ticket": "ticket",
        "checkpoint": "checkpoint",
        "decision": "decision",
        "artifact": "artifact",
        "external-effect": "external_effect",
    }
    if prefix not in kinds or not target_id:
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "source link target")
    return kinds[prefix], target_id


def _safe_title(title: str) -> str:
    if any(
        ord(character) < _CONTROL_CHARACTER_LIMIT or ord(character) == _DELETE_CHARACTER
        for character in title
    ):
        raise MigrationRefusal(RefusalCode.FORBIDDEN_DATA_CLASS, "ticket title controls")
    return title
