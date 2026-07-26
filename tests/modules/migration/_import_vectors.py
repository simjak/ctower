"""Strict synthetic operation vectors consumed by migration storage tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ctower_client.models import (
    CtowerProjectExactAliasOperation,
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportRunCreateRequest,
    CtowerProjectSourceLinkOperation,
    CtowerProjectTicketRelationOperation,
    CtowerProjectTicketSeedOperation,
    MigrationFenceFileIdentity,
    MigrationOperationIdentity,
    MigrationSourceIdentity,
)
from tools.migration.ctower_project.ctower_project_source.canonical import canonical_digest

__all__: tuple[str, ...] = ()
ZERO_DIGEST = f"sha256:{'0' * 64}"


def run_request(credential: str, now: datetime) -> CtowerProjectImportRunCreateRequest:
    return CtowerProjectImportRunCreateRequest(
        cutover_id=uuid4(),
        tenant_key="ctower",
        project_key="ctower",
        source_selection_digest=ZERO_DIGEST,
        source_selection_artifact="{}",
        build_digest=ZERO_DIGEST,
        client_digest=ZERO_DIGEST,
        schema_digest=ZERO_DIGEST,
        operation_registry_digest=ZERO_DIGEST,
        reviewer_key_ref="signing-key-ref:test/reviewer",
        reviewer_key_version=1,
        reviewer_public_key_digest=ZERO_DIGEST,
        importer_credential_digest=f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
        importer_expires_at=now + timedelta(hours=1),
    )


def seed_batch(
    run_id: UUID, cutover_id: UUID, commander_id: UUID, *, batch_index: int
) -> CtowerProjectImportBatchRequest:
    operations = tuple(ticket_seed(source_id, commander_id) for source_id in ("R325", "R326"))
    return batch(run_id, cutover_id, batch_index, operations)


def ticket_seed(source_id: str, commander_id: UUID) -> CtowerProjectTicketSeedOperation:
    return CtowerProjectTicketSeedOperation(
        operation="ticket_seed",
        identity=_identity("ticket_seed", source_id, "new_ticket"),
        project_key="ctower",
        priority="P2",
        title=f"Synthetic {source_id}",
        source=_source(source_id),
        initial_commander_custodian_id=commander_id,
    )


def alias_batch(
    run_id: UUID, cutover_id: UUID, ticket_id: UUID, *, batch_index: int
) -> CtowerProjectImportBatchRequest:
    source_id = "legacy-exact-alias"
    operation = CtowerProjectExactAliasOperation(
        operation="exact_alias",
        identity=_identity("exact_alias", source_id, f"ticket:{ticket_id}"),
        project_key="ctower",
        source=_source(source_id),
        target_ticket_id=ticket_id,
    )
    return batch(run_id, cutover_id, batch_index, (operation,))


def relation_batch(
    run_id: UUID,
    cutover_id: UUID,
    relation_id: UUID,
    source_ticket_id: UUID,
    target_ticket_id: UUID,
    *,
    batch_index: int,
) -> CtowerProjectImportBatchRequest:
    operation = CtowerProjectTicketRelationOperation(
        operation="ticket_relation",
        identity=_identity("ticket_relation", str(relation_id), f"ticket_relation:{relation_id}"),
        project_key="ctower",
        relation_id=relation_id,
        relation_kind="parent_of",
        source_ticket_id=source_ticket_id,
        target_ticket_id=target_ticket_id,
        reason="Synthetic reviewed relation",
    )
    return batch(run_id, cutover_id, batch_index, (operation,))


def source_link_batch(
    run_id: UUID, cutover_id: UUID, ticket_id: UUID, *, batch_index: int
) -> CtowerProjectImportBatchRequest:
    source_id = "legacy-decision"
    operation = CtowerProjectSourceLinkOperation(
        operation="source_link",
        identity=_identity("source_link", source_id, f"ticket:{ticket_id}"),
        project_key="ctower",
        source=_source(source_id),
        link_class="decision",
        target_kind="ticket",
        target_id=f"ticket:{ticket_id}",
        reason_code="reviewed_decision_link",
        linked_not_proof=True,
    )
    return batch(run_id, cutover_id, batch_index, (operation,))


def batch(
    run_id: UUID,
    cutover_id: UUID,
    batch_index: int,
    operations: tuple[object, ...],
) -> CtowerProjectImportBatchRequest:
    seed = {
        "schema": "ctower.ctower-project-import-batch/v1",
        "run_id": str(run_id),
        "cutover_id": str(cutover_id),
        "batch_index": batch_index,
        "operations": [
            item.model_dump(mode="json", by_alias=True)
            for item in operations
            if hasattr(item, "model_dump")
        ],
    }
    return CtowerProjectImportBatchRequest.model_validate(
        {
            **seed,
            "run_id": run_id,
            "cutover_id": cutover_id,
            "operations": operations,
            "batch_digest": canonical_digest(seed),
        }
    )


def fence_request(
    *,
    sequence: int,
    previous: str | None,
    registry_id: UUID | None = None,
) -> CtowerProjectFenceObservationRequest:
    observation_id = uuid4()
    run_id = uuid4()
    cutover_id = uuid4()
    resolved_registry_id = registry_id or uuid4()
    observed_at = datetime.now(UTC)
    body = {
        "schema": "ctower.ctower-project-fence-observation/v2",
        "observation_id": str(observation_id),
        "run_id": str(run_id),
        "cutover_id": str(cutover_id),
        "tenant_key": "ctower",
        "project_key": "ctower",
        "registry_id": str(resolved_registry_id),
        "registry_revision": 1,
        "registry_digest": ZERO_DIGEST,
        "source_pointer_digest": ZERO_DIGEST,
        "sequence": sequence,
        "previous_observation_digest": previous,
        "observed_at": observed_at.isoformat(),
        "from_offset": 0,
        "to_offset": 0,
        "file_identity": MigrationFenceFileIdentity(
            device=1, inode=1, scoped_rows_digest=ZERO_DIGEST
        ).model_dump(mode="json"),
        "status": "unknown",
        "reason_code": "classifier_unknown",
        "disables_writes": True,
        "may_enable_writes": False,
    }
    return CtowerProjectFenceObservationRequest.model_validate(
        {
            **body,
            "observation_id": observation_id,
            "run_id": run_id,
            "cutover_id": cutover_id,
            "registry_id": resolved_registry_id,
            "observed_at": observed_at,
            "observation_digest": canonical_digest(body),
        }
    )


def _identity(operation: str, source_id: str, planned_target: str) -> MigrationOperationIdentity:
    return MigrationOperationIdentity.model_validate(
        {
            "namespace": "mission-control:request",
            "immutable_source_id": source_id,
            "source_version_or_digest": "line:1",
            "operation_kind": operation,
            "planned_target_ref": planned_target,
            "command_id": uuid4(),
        }
    )


def _source(source_id: str) -> MigrationSourceIdentity:
    return MigrationSourceIdentity(
        namespace="mission-control:request",
        immutable_source_id=source_id,
        source_version="line:1",
        source_digest=ZERO_DIGEST,
    )
