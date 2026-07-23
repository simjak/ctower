"""Same-artifact process entry point for fixed scheduler and accepted outbox loops."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from ctower_api._outbox_loop import OutboxLoop
from ctower_api._routine_loop import RoutineLoop, load_routine_revisions
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__ = ["ControlWorker", "build_worker", "main"]

_ROOT = Path(__file__).parents[4]
_MIN_INTERVAL_SECONDS = 0.1
_MAX_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class ControlWorker:
    """Coordinate separately owned loops without owning their durable decisions."""

    runtime: Routine
    routine_loop: RoutineLoop
    outbox_loop: OutboxLoop

    def tick(self) -> None:
        tenant_ids = self.runtime.tenant_ids()
        self.routine_loop.tick(tenant_ids)
        self.outbox_loop.tick(tenant_ids)

    def run(self, stop: Event, *, interval_seconds: float = 1.0) -> None:
        if not _valid_interval(interval_seconds):
            raise ValueError("control worker interval must be between 0.1 and 60 seconds")
        while not stop.is_set():
            self.tick()
            stop.wait(interval_seconds)


def main() -> None:
    """Run the control worker from strict environment references."""

    runtime_dsn = _required_environment("CTOWER_DATABASE_DSN")
    projection_dsn = _required_environment("CTOWER_PROJECTION_DSN")
    interval = _interval(os.environ.get("CTOWER_CONTROL_INTERVAL_SECONDS", "1"))
    pack_root = Path(os.environ.get("CTOWER_PACK_ROOT", str(_ROOT / "packs")))
    runtime = Routine(PostgresRuntime(runtime_dsn))
    projections = Projections(PostgresProjections(projection_dsn))
    worker = build_worker(runtime, projections, pack_root=pack_root)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    worker.run(stop, interval_seconds=interval)


def build_worker(runtime: Routine, projections: Projections, *, pack_root: Path) -> ControlWorker:
    """Compose the same worker around public kernel Interfaces."""

    return ControlWorker(
        runtime,
        RoutineLoop(runtime, load_routine_revisions(pack_root)),
        OutboxLoop(projections),
    )


def _required_environment(key: str) -> str:
    value = os.environ.get(key)
    if value is None or not value.strip():
        raise RuntimeError(f"{key} must name a configured connection reference")
    return value


def _interval(value: str) -> float:
    try:
        interval = float(value)
    except ValueError as error:
        raise ValueError("CTOWER_CONTROL_INTERVAL_SECONDS must be numeric") from error
    if not _valid_interval(interval):
        raise ValueError("CTOWER_CONTROL_INTERVAL_SECONDS is outside the bounded range")
    return interval


def _valid_interval(value: float) -> bool:
    return _MIN_INTERVAL_SECONDS <= value <= _MAX_INTERVAL_SECONDS
