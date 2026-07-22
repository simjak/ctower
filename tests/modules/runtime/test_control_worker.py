"""Same-artifact control worker behavior through public Interfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from ctower_api.control_worker import build_worker
from ctower_kernel.projections import (
    BoardQuery,
    BoardView,
    ControlHealth,
    ProjectionHealth,
    Projections,
)
from ctower_kernel.record import Actor, DurabilityHealth
from ctower_kernel.runtime import Routine, RoutineRevision, SchedulerScan

ROOT = Path(__file__).parents[3]


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


def test_worker_loads_exact_fixed_packs_and_ticks_each_owned_loop() -> None:
    tenant_id = uuid4()
    routine_store = _RoutineStore(tenant_id)
    projection_store = _ProjectionStore()
    runtime = Routine(routine_store)
    projections = Projections(projection_store)
    worker = build_worker(runtime, projections, pack_root=ROOT / "packs")

    worker.tick()

    assert routine_store.registered == [
        "ctower.i1.synthetic-four-stage@1",
        "ctower.i1.daily-backup@1",
        "ctower.i1.record-anchor@1",
    ]
    assert routine_store.scans == 1
    assert projection_store.tenants == [tenant_id]
