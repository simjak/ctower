"""Same-artifact control worker behavior through public Interfaces."""

from __future__ import annotations

import json
import shutil
import signal
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import cast
from uuid import UUID, uuid4

import pytest

import ctower_api.control_worker as control_worker_module
from ctower_api.control_worker import build_worker
from ctower_api.synthetic_handler import SyntheticFourStageHandler
from ctower_kernel.projections import (
    BoardQuery,
    BoardView,
    ControlHealth,
    CtowerProjectCutoverHealth,
    ProjectDeliveryView,
    ProjectionHealth,
    Projections,
)
from ctower_kernel.record import Actor, DurabilityHealth
from ctower_kernel.runtime import (
    FixedOperationAttempt,
    FixedOperationCompletion,
    FixedOperationJob,
    FixedOperations,
    Routine,
    RoutineRevision,
    SchedulerScan,
)

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXPECTED_TICKS = 2
CONTROL_INTERVAL_SECONDS = 0.5


class _RoutineStore:
    def __init__(self, tenant_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.registered: list[str] = []
        self.scans = 0

    def tenant_ids(self) -> tuple[UUID, ...]:
        return (self.tenant_id,)

    def register(
        self,
        tenant_id: UUID,
        revision: RoutineRevision,
        *,
        first_fire_at: datetime | None,
    ) -> None:
        assert tenant_id == self.tenant_id
        assert first_fire_at is None
        self.registered.append(revision.routine_ref)

    def scan(self, tenant_id: UUID) -> SchedulerScan:
        self.scans += 1
        return SchedulerScan(tenant_id, self.scans, datetime.now(UTC), (), ())


class _ProjectionStore:
    def __init__(self) -> None:
        self.tenants: list[UUID] = []
        self.delivery_tenants: list[UUID] = []

    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView:
        assert through_watermark is None
        self.tenants.append(tenant_id)
        return BoardView((), ProjectionHealth.CURRENT, 0, 0)

    def board(self, actor: Actor, query: BoardQuery) -> BoardView:
        raise NotImplementedError

    def rebuild(self, tenant_id: UUID) -> BoardView:
        raise NotImplementedError

    def health(
        self, tenant_id: UUID, durability: DurabilityHealth, *, now: datetime
    ) -> ControlHealth:
        raise NotImplementedError

    def cutover_health(self, actor: Actor) -> CtowerProjectCutoverHealth:
        raise NotImplementedError

    def project_delivery(self, actor: Actor, project_key: str) -> ProjectDeliveryView | None:
        raise NotImplementedError

    def reconcile_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        assert now.tzinfo is not None
        self.delivery_tenants.append(tenant_id)
        return 0

    def rebuild_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        raise NotImplementedError


class _OneTickEvent(Event):
    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        self.set()
        return True


class _MainWorker:
    def __init__(self, observed: dict[str, object]) -> None:
        self._observed = observed

    def run(self, stop: Event, *, interval_seconds: float = 1.0) -> None:
        self._observed["stop"] = stop
        self._observed["interval"] = interval_seconds


class _FixedOperations:
    def __init__(self, attempt: FixedOperationAttempt) -> None:
        self._attempt: FixedOperationAttempt | None = attempt
        self.claims: list[str] = []
        self.completions: list[tuple[FixedOperationAttempt, FixedOperationCompletion]] = []

    def claim_synthetic(self, worker_ref: str) -> FixedOperationAttempt | None:
        self.claims.append(worker_ref)
        attempt, self._attempt = self._attempt, None
        return attempt

    def complete_synthetic(
        self,
        attempt: FixedOperationAttempt,
        completion: FixedOperationCompletion,
    ) -> None:
        self.completions.append((attempt, completion))


class _SyntheticHandler:
    def __init__(self, completion: FixedOperationCompletion) -> None:
        self._completion = completion
        self.attempts: list[FixedOperationAttempt] = []

    def execute(self, attempt: FixedOperationAttempt) -> FixedOperationCompletion:
        self.attempts.append(attempt)
        return self._completion


def test_worker_loads_exact_fixed_packs_and_ticks_each_owned_loop() -> None:
    tenant_id = uuid4()
    routine_store = _RoutineStore(tenant_id)
    projection_store = _ProjectionStore()
    runtime = Routine(routine_store)
    projections = Projections(projection_store)
    worker = build_worker(runtime, projections, pack_root=ROOT / "packs")

    worker.tick()
    worker.run(_OneTickEvent(), interval_seconds=0.1)

    assert (
        routine_store.registered
        == [
            "ctower.i1.synthetic-four-stage@1",
            "ctower.i1.daily-backup@1",
            "ctower.i1.record-anchor@1",
        ]
        * EXPECTED_TICKS
    )
    assert routine_store.scans == EXPECTED_TICKS
    assert projection_store.tenants == [tenant_id, tenant_id]
    assert projection_store.delivery_tenants == [tenant_id, tenant_id]
    with pytest.raises(ValueError, match="interval"):
        worker.run(Event(), interval_seconds=0.0)


def test_worker_tick_claims_executes_and_completes_synthetic_operation() -> None:
    tenant_id = uuid4()
    now = datetime.now(UTC)
    job = FixedOperationJob(
        uuid4(),
        tenant_id,
        uuid4(),
        "synthetic_four_stage",
        60,
        (),
        now,
    )
    attempt = FixedOperationAttempt(
        uuid4(),
        job,
        1,
        uuid4(),
        "test-worker",
        now,
        now + timedelta(seconds=30),
    )
    completion = FixedOperationCompletion(
        succeeded=True,
        ticket_id=uuid4(),
        lifecycle_facts=("resolved", "closed"),
        detail_code="synthetic-four-stage-complete",
    )
    fixed = _FixedOperations(attempt)
    handler = _SyntheticHandler(completion)
    worker = build_worker(
        Routine(_RoutineStore(tenant_id)),
        Projections(_ProjectionStore()),
        pack_root=ROOT / "packs",
        fixed_operations=cast(FixedOperations, fixed),
        synthetic_handler=handler,
    )

    worker.tick()

    assert fixed.claims == ["ctower.control-worker.synthetic"]
    assert handler.attempts == [attempt]
    assert fixed.completions == [(attempt, completion)]


def test_worker_main_and_environment_boundary_are_strict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, object] = {}

    def fake_build_worker(
        runtime: Routine,
        projections: Projections,
        *,
        pack_root: Path,
        fixed_operations: FixedOperations | None = None,
        synthetic_handler: object | None = None,
    ) -> _MainWorker:
        observed["runtime"] = runtime
        observed["projections"] = projections
        observed["pack_root"] = pack_root
        observed["fixed_operations"] = fixed_operations
        observed["synthetic_handler"] = synthetic_handler
        return _MainWorker(observed)

    monkeypatch.setattr(control_worker_module, "build_worker", fake_build_worker)
    monkeypatch.setattr(signal, "signal", lambda *_args: None)
    monkeypatch.setenv("CTOWER_DATABASE_DSN", "postgresql://runtime-reference")
    monkeypatch.setenv("CTOWER_PROJECTION_DSN", "postgresql://projection-reference")
    monkeypatch.setenv("CTOWER_CONTROL_API_BASE_URL", "https://ctower.invalid")
    monkeypatch.setenv("CTOWER_SYNTHETIC_AUTHOR_CREDENTIAL", "author-credential")
    monkeypatch.setenv("CTOWER_SYNTHETIC_REVIEWER_CREDENTIAL", "reviewer-credential")
    monkeypatch.setenv("CTOWER_SYNTHETIC_AUTHOR_ID", str(uuid4()))
    digest = "sha256:" + "a" * 64
    monkeypatch.setenv("CTOWER_SYNTHETIC_WORKFLOW_DIGEST", digest)
    monkeypatch.setenv("CTOWER_SYNTHETIC_EXECUTION_POLICY_DIGEST", digest)
    monkeypatch.setenv("CTOWER_SYNTHETIC_GATE_POLICY_DIGEST", digest)
    monkeypatch.setenv("CTOWER_SYNTHETIC_EVIDENCE_POLICY_DIGEST", digest)
    monkeypatch.setenv("CTOWER_CONTROL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("CTOWER_PACK_ROOT", str(tmp_path))

    control_worker_module.main()

    assert observed["pack_root"] == tmp_path
    assert observed["interval"] == CONTROL_INTERVAL_SECONDS
    assert isinstance(observed["stop"], Event)
    assert isinstance(observed["fixed_operations"], FixedOperations)
    assert isinstance(observed["synthetic_handler"], SyntheticFourStageHandler)
    monkeypatch.delenv("CTOWER_DATABASE_DSN")
    with pytest.raises(RuntimeError, match="CTOWER_DATABASE_DSN"):
        control_worker_module._required_environment("CTOWER_DATABASE_DSN")
    monkeypatch.setenv("CTOWER_DATABASE_DSN", "   ")
    with pytest.raises(RuntimeError, match="CTOWER_DATABASE_DSN"):
        control_worker_module._required_environment("CTOWER_DATABASE_DSN")
    with pytest.raises(ValueError, match="numeric"):
        control_worker_module._interval("not-a-number")
    with pytest.raises(ValueError, match="bounded"):
        control_worker_module._interval("60.1")
    monkeypatch.setenv("INVALID_UUID", "not-a-uuid")
    with pytest.raises(RuntimeError, match="UUID"):
        control_worker_module._required_uuid("INVALID_UUID")
    monkeypatch.setenv("INVALID_DIGEST", "sha256:ABC")
    with pytest.raises(RuntimeError, match="lowercase sha256"):
        control_worker_module._required_digest("INVALID_DIGEST")


def test_routine_pack_loader_rejects_every_untyped_or_non_exact_shape(tmp_path: Path) -> None:
    authored = ROOT / "packs/routines/ctower.i1.daily-backup/v1.yaml"
    baseline = cast(dict[str, object], json.loads(authored.read_text(encoding="utf-8")))
    schedule = cast(dict[str, object], baseline["schedule"])
    malformed: tuple[object, ...] = (
        [],
        {**baseline, "unexpected": True},
        {**baseline, "schedule": {**schedule, "unexpected": True}},
        {**baseline, "schema_id": "unsupported"},
        {**baseline, "routine_ref": 7},
        {**baseline, "catch_up_cap": True},
        {**baseline, "component_digests": "not-an-array"},
        {**baseline, "schedule": {**schedule, "local_time": "not-a-time"}},
        {**baseline, "schedule": {**schedule, "local_time": "01:00:00.000001"}},
        {**baseline, "routine_ref": "ctower.i1.not-one-of-three@1"},
    )
    for index, invalid in enumerate(malformed):
        case_root = tmp_path / str(index)
        shutil.copytree(ROOT / "packs/routines", case_root / "routines")
        target = case_root / "routines/ctower.i1.daily-backup/v1.yaml"
        target.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises((TypeError, ValueError)):
            build_worker(
                Routine(_RoutineStore(uuid4())),
                Projections(_ProjectionStore()),
                pack_root=case_root,
            )


def test_routine_pack_loader_recomputes_revision_digest_from_authored_content(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "digest-mismatch"
    shutil.copytree(ROOT / "packs/routines", case_root / "routines")
    target = case_root / "routines/ctower.i1.daily-backup/v1.yaml"
    pack = cast(dict[str, object], json.loads(target.read_text(encoding="utf-8")))
    target.write_text(json.dumps({**pack, "timeout_seconds": 7201}), encoding="utf-8")

    with pytest.raises(ValueError, match="revision digest does not match authored content"):
        build_worker(
            Routine(_RoutineStore(uuid4())),
            Projections(_ProjectionStore()),
            pack_root=case_root,
        )
