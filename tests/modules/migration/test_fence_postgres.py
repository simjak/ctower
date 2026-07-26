"""Exact signed-registry fence evidence tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from ctower_client.models import CtowerProjectFenceObservationRequest
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    canonical_digest,
)

from ._postgres import Database, semantic_counts
from ._reviewed import reviewed_source
from .source_tool.fixtures import CUTOVER_ID

__all__: tuple[str, ...] = ()


def test_fence_observer_is_exact_registry_scoped_and_digest_recomputed(
    migration_database: Database,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    source = reviewed_source(tmp_path, CUTOVER_ID)
    store = PostgresMigration(
        migration_database.runtime_dsn,
        trusted_reviewer_keys=source.trusted_keys,
    )
    migration = Migration(store, clock=lambda: now)
    operator = Actor(
        migration_database.operator_id,
        migration_database.tenant_id,
        PrincipalKind.OPERATOR,
    )
    created = migration.create_run(
        operator,
        source.create_request(now),
        command_id=uuid4(),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(created, RecordProblem)
    exported = migration.bind_export_equality(
        operator,
        source.export_request(created.run_id),
        command_id=uuid4(),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(exported, RecordProblem)
    target = _create_target(migration_database, operator)
    plan_request, _plan = source.plan_request(
        created.run_id,
        target,
        migration_database.commander_id,
        now,
    )
    planned = migration.bind_alias_plan(
        operator,
        plan_request,
        command_id=uuid4(),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(planned, RecordProblem)
    observer = store.resolve_fence_observer(
        hashlib.sha256(source.observer_credential.encode()).digest(),
        now,
    )
    assert observer is not None
    registry = json.loads(plan_request.fence_registry_artifact)
    first = _observation(created.run_id, registry, sequence=1, previous=None)
    command_id = uuid4()
    receipt = migration.report_fence_observation(
        observer,
        first,
        command_id=command_id,
        telemetry=_telemetry(observer),
    )
    assert not isinstance(receipt, RecordProblem)

    _assert_replay_and_refusals(
        migration,
        observer,
        created.run_id,
        registry,
        first,
        command_id,
        receipt,
        migration_database,
    )


def _assert_replay_and_refusals(
    migration: Migration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    first: CtowerProjectFenceObservationRequest,
    command_id: UUID,
    receipt: object,
    database: Database,
) -> None:
    _assert_replay(migration, observer, first, command_id, receipt)
    before = semantic_counts(database)
    rebound = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
    ).model_copy(update={"observation_digest": f"sha256:{'f' * 64}"})
    _assert_refused(migration, observer, rebound, uuid4())
    _assert_refused(migration, observer, rebound, command_id)
    unsafe = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
    ).model_copy(update={"disables_writes": False})
    unsafe = _with_digest(unsafe)
    _assert_refused(migration, observer, unsafe, uuid4())
    unclear = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
    ).model_copy(update={"status": "clear"})
    _assert_refused(migration, observer, _with_digest(unclear), uuid4())
    wrong_registry = {**registry, "revision": 2}
    _assert_refused(
        migration,
        observer,
        _observation(run_id, wrong_registry, sequence=2, previous=first.observation_digest),
        uuid4(),
    )
    gap = _observation(run_id, registry, sequence=3, previous=first.observation_digest)
    _assert_refused(migration, observer, gap, uuid4())
    assert semantic_counts(database) == before
    second = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
    )
    continued = migration.report_fence_observation(
        observer,
        second,
        command_id=uuid4(),
        telemetry=_telemetry(observer),
    )
    assert not isinstance(continued, RecordProblem)


def _assert_replay(
    migration: Migration,
    observer: Actor,
    request: CtowerProjectFenceObservationRequest,
    command_id: UUID,
    receipt: object,
) -> None:
    replay = migration.report_fence_observation(
        observer,
        request,
        command_id=command_id,
        telemetry=_telemetry(observer),
    )
    assert replay == receipt


def _assert_refused(
    migration: Migration,
    observer: Actor,
    request: CtowerProjectFenceObservationRequest,
    command_id: UUID,
) -> None:
    outcome = migration.report_fence_observation(
        observer,
        request,
        command_id=command_id,
        telemetry=_telemetry(observer),
    )
    assert isinstance(outcome, RecordProblem)


def _with_digest(
    request: CtowerProjectFenceObservationRequest,
) -> CtowerProjectFenceObservationRequest:
    body = request.model_dump(mode="json", by_alias=True)
    body.pop("observation_digest")
    return request.model_copy(update={"observation_digest": canonical_digest(body)})


def _observation(
    run_id: UUID,
    registry: dict[str, object],
    *,
    sequence: int,
    previous: str | None,
) -> CtowerProjectFenceObservationRequest:
    body: dict[str, object] = {
        "schema": "ctower.ctower-project-fence-observation/v1",
        "observation_id": str(uuid4()),
        "run_id": str(run_id),
        "cutover_id": registry["cutover_id"],
        "tenant_key": "ctower",
        "project_key": "ctower",
        "registry_id": registry["registry_id"],
        "registry_revision": registry["revision"],
        "registry_digest": registry["registry_digest"],
        "sequence": sequence,
        "previous_observation_digest": previous,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "from_offset": 0,
        "to_offset": 0,
        "file_identity": {
            "device": 1,
            "inode": 1,
            "scoped_rows_digest": registry["operation_registry_digest"],
        },
        "status": "unknown",
        "reason_code": "classifier_unknown",
        "disables_writes": True,
        "may_enable_writes": False,
    }
    body["observation_digest"] = canonical_digest(body)
    return CtowerProjectFenceObservationRequest.model_validate_json(canonical_bytes(body))


def _create_target(database: Database, operator: Actor) -> UUID:
    result = Work(PostgresRecord(database.runtime_dsn)).create_ticket(
        operator,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=database.commander_id,
            priority="P2",
            source=SourceReference("synthetic", "synthetic:fence-target"),
            title="Fence graph target",
        ),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(result, RecordProblem)
    return result.ticket.ticket_id


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
