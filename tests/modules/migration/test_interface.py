"""Capability-first behavior through the public Migration Interface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from ctower_client.models import (
    CtowerProjectFenceObservationRequest,
    CtowerProjectImportBatchRequest,
    CtowerProjectImportRunCreateRequest,
)
from ctower_kernel.migration import Migration
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
ZERO_DIGEST = f"sha256:{'0' * 64}"


class _Store:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_run(self, *args: object, **kwargs: object) -> RecordProblem:
        del args, kwargs
        self.calls.append("create")
        return _problem()

    def apply_batch(self, *args: object, **kwargs: object) -> RecordProblem:
        del args, kwargs
        self.calls.append("apply")
        return _problem()

    def report_fence_observation(self, *args: object, **kwargs: object) -> RecordProblem:
        del args, kwargs
        self.calls.append("fence")
        return _problem()


def test_importer_reaches_only_batch_authority() -> None:
    store = _Store()
    migration = Migration(cast(Any, store))
    tenant_id = uuid4()
    importer = Actor(uuid4(), tenant_id, PrincipalKind.MIGRATION_IMPORTER)
    operator = Actor(uuid4(), tenant_id, PrincipalKind.OPERATOR)
    create = _create_request()
    batch = _empty_batch()

    denied_create = migration.create_run(
        importer, create, command_id=uuid4(), telemetry=_telemetry()
    )
    denied_apply = migration.apply_batch(operator, batch, telemetry=_telemetry())
    accepted_apply = migration.apply_batch(
        importer, batch, command_id=uuid4(), telemetry=_telemetry()
    )

    assert isinstance(denied_create, RecordProblem)
    assert isinstance(denied_apply, RecordProblem)
    assert denied_create.code == denied_apply.code == "migration-capability-denied"
    assert isinstance(accepted_apply, RecordProblem)
    assert store.calls == ["apply"]


def test_fence_observer_cannot_borrow_operator_or_importer_authority() -> None:
    store = _Store()
    migration = Migration(cast(Any, store))
    tenant_id = uuid4()
    observer = Actor(uuid4(), tenant_id, PrincipalKind.FENCE_OBSERVER)
    operator = Actor(uuid4(), tenant_id, PrincipalKind.OPERATOR)

    denied_create = migration.create_run(
        observer, _create_request(), command_id=uuid4(), telemetry=_telemetry()
    )
    denied_fence = migration.report_fence_observation(
        operator, _fence_request(), command_id=uuid4(), telemetry=_telemetry()
    )
    accepted_fence = migration.report_fence_observation(
        observer, _fence_request(), command_id=uuid4(), telemetry=_telemetry()
    )

    assert isinstance(denied_create, RecordProblem)
    assert isinstance(denied_fence, RecordProblem)
    assert isinstance(accepted_fence, RecordProblem)
    assert store.calls == ["fence"]


def _create_request() -> CtowerProjectImportRunCreateRequest:
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
        importer_credential_digest=ZERO_DIGEST,
        importer_expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def _empty_batch() -> CtowerProjectImportBatchRequest:
    return cast(CtowerProjectImportBatchRequest, object())


def _fence_request() -> CtowerProjectFenceObservationRequest:
    return cast(CtowerProjectFenceObservationRequest, object())


def _problem() -> RecordProblem:
    return RecordProblem("test", "test", 409, "test")


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )
