"""Exact signed-registry fence evidence tests."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from ctower_client.models import CtowerProjectFenceObservationRequest
from ctower_kernel.migration import Migration, PostgresMigration
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
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
    migration, store, operator, observer, run_id, registry, credential = _start_observer(
        migration_database,
        tmp_path,
        now,
    )
    first = _observation(
        run_id,
        registry,
        sequence=1,
        previous=None,
        observed_at=datetime.now(UTC) - timedelta(seconds=89),
        status="clear",
        reason_code="no_scoped_append",
        disables_writes=False,
    )
    command_id = uuid4()
    receipt = migration.report_fence_observation(
        observer,
        first,
        command_id=command_id,
        telemetry=_telemetry(observer),
    )
    assert not isinstance(receipt, RecordProblem)
    _assert_current_freshness(migration_database, operator)
    latest = _assert_replay_and_refusals(
        migration,
        observer,
        run_id,
        registry,
        first,
        command_id,
        receipt,
        migration_database,
    )
    _assert_canonical_revocation(
        migration_database,
        migration,
        store,
        observer,
        run_id,
        registry,
        credential,
        latest,
    )


def _start_observer(
    database: Database,
    tmp_path: Path,
    now: datetime,
) -> tuple[Migration, PostgresMigration, Actor, Actor, UUID, dict[str, object], bytes]:
    source = reviewed_source(tmp_path, CUTOVER_ID)
    store = PostgresMigration(
        database.runtime_dsn,
        trusted_reviewer_keys=source.trusted_keys,
    )
    migration = Migration(store, clock=lambda: now)
    operator = Actor(database.operator_id, database.tenant_id, PrincipalKind.OPERATOR)
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
    plan_request, _plan = source.plan_request(
        created.run_id,
        _create_target(database, operator),
        database.commander_id,
        now,
    )
    planned = migration.bind_alias_plan(
        operator,
        plan_request,
        command_id=uuid4(),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(planned, RecordProblem)
    credential = hashlib.sha256(source.observer_credential.encode()).digest()
    observer = store.resolve_fence_observer(credential, now)
    assert observer is not None
    return (
        migration,
        store,
        operator,
        observer,
        created.run_id,
        json.loads(plan_request.fence_registry_artifact),
        credential,
    )


def _assert_current_freshness(database: Database, operator: Actor) -> None:
    projections = Projections(PostgresProjections(database.projection_dsn))
    assert projections.cutover_health(operator).split_brain == "clear"
    time.sleep(2)
    assert projections.cutover_health(operator).split_brain == "unknown"


def _assert_canonical_revocation(
    database: Database,
    migration: Migration,
    store: PostgresMigration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    credential: bytes,
    latest: CtowerProjectFenceObservationRequest,
) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        changed = connection.execute(
            """
            UPDATE principal_credentials
            SET revoked_at = %s
            WHERE tenant_id = %s AND principal_id = %s
              AND credential_digest = %s AND revoked_at IS NULL
            """,
            (
                datetime.now(UTC),
                observer.tenant_id,
                observer.principal_id,
                credential,
            ),
        )
        assert changed.rowcount == 1
    assert store.resolve_fence_observer(credential, datetime.now(UTC)) is None
    revoked_candidate = _observation(
        run_id,
        registry,
        sequence=latest.sequence + 1,
        previous=latest.observation_digest,
        status="detected",
        reason_code="scoped_row_appended",
        disables_writes=True,
    )
    before_revoked = semantic_counts(database)
    _assert_refused(migration, observer, revoked_candidate, uuid4())
    assert semantic_counts(database) == before_revoked


def _assert_replay_and_refusals(
    migration: Migration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    first: CtowerProjectFenceObservationRequest,
    command_id: UUID,
    receipt: object,
    database: Database,
) -> CtowerProjectFenceObservationRequest:
    _assert_replay(migration, observer, first, command_id, receipt)
    before = semantic_counts(database)
    _assert_shape_refusals(migration, observer, run_id, registry, first, command_id)
    _assert_temporal_refusals(migration, observer, run_id, registry, first)
    assert semantic_counts(database) == before
    return _assert_sticky_degradation(migration, observer, run_id, registry, first, database)


def _assert_shape_refusals(
    migration: Migration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    first: CtowerProjectFenceObservationRequest,
    command_id: UUID,
) -> None:
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


def _assert_temporal_refusals(
    migration: Migration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    first: CtowerProjectFenceObservationRequest,
) -> None:
    stale = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        observed_at=datetime.now(UTC) - timedelta(seconds=91),
        status="clear",
        reason_code="no_scoped_append",
        disables_writes=False,
    )
    _assert_refused(migration, observer, stale, uuid4())
    future = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        observed_at=datetime.now(UTC) + timedelta(seconds=6),
        status="clear",
        reason_code="no_scoped_append",
        disables_writes=False,
    )
    _assert_refused(migration, observer, future, uuid4())
    reversed_offsets = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        from_offset=1,
        to_offset=0,
    )
    _assert_refused(migration, observer, reversed_offsets, uuid4())
    discontinuity = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        from_offset=1,
        to_offset=1,
    )
    _assert_refused(migration, observer, discontinuity, uuid4())
    wrong_pointer = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        source_pointer_digest=f"sha256:{'0' * 64}",
    )
    _assert_refused(migration, observer, wrong_pointer, uuid4())
    wrong_identity = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
    ).model_copy(
        update={
            "file_identity": first.file_identity.model_copy(
                update={"inode": first.file_identity.inode + 1}
            )
        }
    )
    _assert_refused(migration, observer, _with_digest(wrong_identity), uuid4())


def _assert_sticky_degradation(
    migration: Migration,
    observer: Actor,
    run_id: UUID,
    registry: dict[str, object],
    first: CtowerProjectFenceObservationRequest,
    database: Database,
) -> CtowerProjectFenceObservationRequest:
    second = _observation(
        run_id,
        registry,
        sequence=2,
        previous=first.observation_digest,
        status="clear",
        reason_code="no_scoped_append",
        disables_writes=False,
    )
    continued = migration.report_fence_observation(
        observer,
        second,
        command_id=uuid4(),
        telemetry=_telemetry(observer),
    )
    assert not isinstance(continued, RecordProblem)
    degraded = _observation(
        run_id,
        registry,
        sequence=3,
        previous=second.observation_digest,
        status="unknown",
        reason_code="classifier_unknown",
        disables_writes=True,
    )
    degraded_receipt = migration.report_fence_observation(
        observer,
        degraded,
        command_id=uuid4(),
        telemetry=_telemetry(observer),
    )
    assert not isinstance(degraded_receipt, RecordProblem)
    recovery = _observation(
        run_id,
        registry,
        sequence=4,
        previous=degraded.observation_digest,
        status="clear",
        reason_code="no_scoped_append",
        disables_writes=False,
    )
    before_recovery = semantic_counts(database)
    _assert_refused(migration, observer, recovery, uuid4())
    assert semantic_counts(database) == before_recovery
    return degraded


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
    observed_at: datetime | None = None,
    from_offset: int = 0,
    to_offset: int = 0,
    source_pointer_digest: str | None = None,
    status: str = "unknown",
    reason_code: str = "classifier_unknown",
    disables_writes: bool = True,
) -> CtowerProjectFenceObservationRequest:
    body: dict[str, object] = {
        "schema": "ctower.ctower-project-fence-observation/v2",
        "observation_id": str(uuid4()),
        "run_id": str(run_id),
        "cutover_id": registry["cutover_id"],
        "tenant_key": "ctower",
        "project_key": "ctower",
        "registry_id": registry["registry_id"],
        "registry_revision": registry["revision"],
        "registry_digest": registry["registry_digest"],
        "source_pointer_digest": (source_pointer_digest or registry["source_pointer_digest"]),
        "sequence": sequence,
        "previous_observation_digest": previous,
        "observed_at": (observed_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        "from_offset": from_offset,
        "to_offset": to_offset,
        "file_identity": {
            "device": 1,
            "inode": 1,
            "scoped_rows_digest": registry["operation_registry_digest"],
        },
        "status": status,
        "reason_code": reason_code,
        "disables_writes": disables_writes,
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
