"""PostgreSQL monotonicity tests for dormant fence observations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

from ._import_vectors import fence_request
from ._postgres import Database, add_fence_observer, semantic_counts

__all__: tuple[str, ...] = ()


def test_fence_observations_are_contiguous_and_degrade_only(
    migration_database: Database,
) -> None:
    observer = add_fence_observer(migration_database)
    now = datetime.now(UTC)
    migration = Migration(PostgresMigration(migration_database.runtime_dsn), clock=lambda: now)
    request = fence_request(sequence=1, previous=None)
    command_id = uuid4()

    receipt = migration.report_fence_observation(
        observer, request, command_id=command_id, telemetry=_telemetry(observer)
    )
    assert not isinstance(receipt, RecordProblem)
    before = semantic_counts(migration_database)
    replayed = migration.report_fence_observation(
        observer, request, command_id=command_id, telemetry=_telemetry(observer)
    )
    assert replayed == receipt
    assert semantic_counts(migration_database) == before
    clear = fence_request(
        sequence=2,
        previous=request.observation_digest,
        registry_id=request.registry_id,
    ).model_copy(
        update={
            "status": "clear",
            "reason_code": "no_scoped_append",
            "disables_writes": False,
        }
    )
    refused_clear = migration.report_fence_observation(
        observer, clear, command_id=uuid4(), telemetry=_telemetry(observer)
    )
    assert isinstance(refused_clear, RecordProblem)
    assert semantic_counts(migration_database) == before
    stale = fence_request(
        sequence=2,
        previous=f"sha256:{'f' * 64}",
        registry_id=request.registry_id,
    )
    refused = migration.report_fence_observation(
        observer, stale, command_id=uuid4(), telemetry=_telemetry(observer)
    )
    assert isinstance(refused, RecordProblem)
    assert semantic_counts(migration_database) == before


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
