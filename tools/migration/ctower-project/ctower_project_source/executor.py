"""Explicit generated-client-only import execution and exact replay proof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid5

from ctower_client.models import (
    CtowerProjectImportBatchRequest,
    CtowerProjectImportBatchResult,
)

from .canonical import canonical_bytes
from .import_plan import ImportPlan
from .refusal import MigrationRefusal, RefusalCode

__all__ = (
    "DryRunReceipt",
    "GeneratedImportClient",
    "ImportPassReceipt",
    "batch_command_id",
    "execute_import",
    "prove_pass_two",
)

_BATCH_COMMAND_NAMESPACE = UUID("5b0e2050-794d-5f39-ae31-c1fd1ab932b4")


class GeneratedImportClient(Protocol):
    def apply_ctower_project_import_batch(
        self,
        request: CtowerProjectImportBatchRequest,
        *,
        command_id: UUID,
    ) -> CtowerProjectImportBatchResult: ...


@dataclass(frozen=True)
class ImportPassReceipt:
    run_id: UUID
    cutover_id: UUID
    batches: tuple[CtowerProjectImportBatchResult, ...]

    @property
    def operation_count(self) -> int:
        return sum(len(batch.results) for batch in self.batches)


@dataclass(frozen=True)
class DryRunReceipt:
    run_id: UUID
    cutover_id: UUID
    batch_count: int
    operation_count: int
    plan_digest: str
    applied: bool = False


def execute_import(
    plan: ImportPlan,
    *,
    client: GeneratedImportClient | None = None,
    apply: bool = False,
    completed: tuple[CtowerProjectImportBatchResult, ...] = (),
    progress: Callable[[CtowerProjectImportBatchResult], None] | None = None,
) -> DryRunReceipt | ImportPassReceipt:
    if not apply:
        return DryRunReceipt(
            plan.run_id,
            plan.cutover_id,
            len(plan.batches),
            plan.operation_count,
            plan.plan_digest,
        )
    if client is None:
        raise MigrationRefusal(RefusalCode.MUTATION_NOT_EXPLICIT, "generated client required")
    accumulated = list(_validate_completed(plan, completed))
    for batch in plan.batches[len(accumulated) :]:
        _validate_scope(plan, batch)
        result = client.apply_ctower_project_import_batch(
            batch,
            command_id=batch_command_id(batch),
        )
        _validate_result(batch, result)
        accumulated.append(result)
        if progress is not None:
            progress(result)
    return ImportPassReceipt(plan.run_id, plan.cutover_id, tuple(accumulated))


def batch_command_id(batch: CtowerProjectImportBatchRequest) -> UUID:
    return uuid5(
        _BATCH_COMMAND_NAMESPACE,
        f"{batch.run_id}:{batch.cutover_id}:{batch.batch_index}:{batch.batch_digest}",
    )


def prove_pass_two(first: ImportPassReceipt, second: ImportPassReceipt) -> None:
    if (
        first.run_id != second.run_id
        or first.cutover_id != second.cutover_id
        or len(first.batches) != len(second.batches)
    ):
        raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "pass scope")
    for original, replay in zip(first.batches, second.batches, strict=True):
        if any(result.replayed for result in original.results):
            raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "pass one replay marker")
        if any(not result.replayed for result in replay.results):
            raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "pass two replay marker")
        if canonical_bytes(_normalized_result(original)) != canonical_bytes(
            _normalized_result(replay)
        ):
            raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "batch response")


def _validate_completed(
    plan: ImportPlan,
    completed: tuple[CtowerProjectImportBatchResult, ...],
) -> tuple[CtowerProjectImportBatchResult, ...]:
    if len(completed) > len(plan.batches):
        raise MigrationRefusal(RefusalCode.IMPORT_SEQUENCE_GAP, "completed batch count")
    for index, result in enumerate(completed):
        expected = plan.batches[index]
        _validate_result(expected, result)
    return completed


def _validate_scope(plan: ImportPlan, batch: CtowerProjectImportBatchRequest) -> None:
    if batch.run_id != plan.run_id or batch.cutover_id != plan.cutover_id:
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "batch tuple")


def _validate_result(
    request: CtowerProjectImportBatchRequest,
    result: CtowerProjectImportBatchResult,
) -> None:
    if (
        result.run_id != request.run_id
        or result.batch_index != request.batch_index
        or result.batch_digest != request.batch_digest
        or len(result.results) != len(request.operations)
    ):
        raise MigrationRefusal(RefusalCode.IMPORT_SCOPE_MISMATCH, "batch result")
    requested = [item.identity.command_id for item in request.operations]
    returned = [item.command_id for item in result.results]
    if requested != returned:
        raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "operation results")


def _normalized_result(result: CtowerProjectImportBatchResult) -> dict[str, object]:
    payload = result.model_dump(mode="json", by_alias=True)
    operations = payload["results"]
    if not isinstance(operations, list):
        raise MigrationRefusal(RefusalCode.IMPORT_REPLAY_DRIFT, "result shape")
    for operation in operations:
        if isinstance(operation, dict):
            operation["replayed"] = False
    return payload
