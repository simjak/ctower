"""Same-artifact process entry point for fixed scheduler and accepted outbox loops."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol
from uuid import UUID

from ctower_api._outbox_loop import OutboxLoop
from ctower_api._project_delivery_loop import ProjectDeliveryLoop
from ctower_api._routine_loop import RoutineLoop, load_routine_revisions
from ctower_api.connector_loop import build_active_connector_loops
from ctower_api.synthetic_handler import (
    SyntheticFourStageHandler,
    SyntheticPolicyPins,
    SyntheticRetryError,
)
from ctower_client import CtowerClient, CtowerProblemError
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import (
    Actor,
    DurabilityFinalizationBatch,
    DurabilityFinalizer,
    PrincipalKind,
)
from ctower_kernel.runtime import (
    FixedOperationAttempt,
    FixedOperationCompletion,
    FixedOperations,
    Routine,
    RoutineRevision,
)
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__ = ["ControlWorker", "build_worker", "load_routine_revisions", "main"]

_ROOT = Path(__file__).parents[4]
_MIN_INTERVAL_SECONDS = 0.1
_MAX_INTERVAL_SECONDS = 60.0
_DIGEST_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class _SyntheticHandler(Protocol):
    def execute(self, attempt: FixedOperationAttempt) -> FixedOperationCompletion: ...


class _DurabilityProgressRecorder(Protocol):
    def completed(self, batch: DurabilityFinalizationBatch) -> None: ...

    def failed(self) -> None: ...


class _StandingIntegration(Protocol):
    def tick(self) -> object: ...


@dataclass(frozen=True, slots=True)
class ControlWorker:
    """Coordinate separately owned loops without owning their durable decisions."""

    runtime: Routine
    routine_loop: RoutineLoop
    outbox_loop: OutboxLoop
    project_delivery_loop: ProjectDeliveryLoop
    durability_finalizer: DurabilityFinalizer | None = None
    durability_progress: _DurabilityProgressRecorder | None = None
    fixed_operations: FixedOperations | None = None
    synthetic_handler: _SyntheticHandler | None = None
    standing_integrations: tuple[_StandingIntegration, ...] = ()

    def tick(self) -> None:
        self._tick_finalizer()
        tenant_ids = self.runtime.tenant_ids()
        self.routine_loop.tick(tenant_ids)
        self.outbox_loop.tick(tenant_ids)
        self.project_delivery_loop.tick(tenant_ids)
        for integration in self.standing_integrations:
            integration.tick()
        self._tick_synthetic()

    def _tick_finalizer(self) -> None:
        if self.durability_finalizer is None:
            return
        batch: DurabilityFinalizationBatch | None = None
        try:
            batch = self.durability_finalizer.finalize_pending()
        finally:
            self._record_finalizer_progress(batch)

    def _record_finalizer_progress(self, batch: DurabilityFinalizationBatch | None) -> None:
        if self.durability_progress is None:
            return
        if batch is None:
            self.durability_progress.failed()
        else:
            self.durability_progress.completed(batch)

    def run(self, stop: Event, *, interval_seconds: float = 1.0) -> None:
        if not _valid_interval(interval_seconds):
            raise ValueError("control worker interval must be between 0.1 and 60 seconds")
        while not stop.is_set():
            self.tick()
            stop.wait(interval_seconds)

    def _tick_synthetic(self) -> None:
        if self.fixed_operations is None or self.synthetic_handler is None:
            return
        attempt = self.fixed_operations.claim_synthetic("ctower.control-worker.synthetic")
        if attempt is None:
            return
        try:
            completion = self.synthetic_handler.execute(attempt)
        except SyntheticRetryError:
            return
        except CtowerProblemError as error:
            completion = FixedOperationCompletion(
                succeeded=False,
                ticket_id=None,
                lifecycle_facts=(),
                detail_code=f"synthetic-{error.problem.code}",
            )
        self.fixed_operations.complete_synthetic(attempt, completion)


def main() -> None:
    """Run the control worker from strict environment references."""

    runtime_dsn = _required_environment("CTOWER_DATABASE_DSN")
    projection_dsn = _required_environment("CTOWER_PROJECTION_DSN")
    api_base_url = _required_environment("CTOWER_CONTROL_API_BASE_URL")
    author_credential = _required_environment("CTOWER_SYNTHETIC_AUTHOR_CREDENTIAL")
    reviewer_credential = _required_environment("CTOWER_SYNTHETIC_REVIEWER_CREDENTIAL")
    if author_credential == reviewer_credential:
        raise RuntimeError("synthetic author and reviewer credentials must be distinct")
    author_id = _required_uuid("CTOWER_SYNTHETIC_AUTHOR_ID")
    tenant_id = _required_uuid("CTOWER_TENANT_ID")
    pins = SyntheticPolicyPins(
        workflow_digest=_required_digest("CTOWER_SYNTHETIC_WORKFLOW_DIGEST"),
        execution_policy_digest=_required_digest("CTOWER_SYNTHETIC_EXECUTION_POLICY_DIGEST"),
        gate_policy_digest=_required_digest("CTOWER_SYNTHETIC_GATE_POLICY_DIGEST"),
        evidence_policy_digest=_required_digest("CTOWER_SYNTHETIC_EVIDENCE_POLICY_DIGEST"),
    )
    interval = _interval(os.environ.get("CTOWER_CONTROL_INTERVAL_SECONDS", "1"))
    pack_root = Path(os.environ.get("CTOWER_PACK_ROOT", str(_ROOT / "packs")))
    runtime_store = PostgresRuntime(runtime_dsn)
    runtime = Routine(runtime_store)
    projections = Projections(PostgresProjections(projection_dsn))
    fixed_operations = FixedOperations(runtime_store)
    with (
        CtowerClient(api_base_url, credential=author_credential) as author,
        CtowerClient(api_base_url, credential=reviewer_credential) as reviewer,
    ):
        standing_integrations = build_active_connector_loops(
            author.export_company_bundle(),
            actor=Actor(author_id, tenant_id, PrincipalKind.COMMANDER),
            runtime_dsn=runtime_dsn,
            resolve_secret=_required_environment,
        )
        worker = build_worker(
            runtime,
            projections,
            pack_root=pack_root,
            fixed_operations=fixed_operations,
            synthetic_handler=SyntheticFourStageHandler(author, reviewer, author_id, pins),
            standing_integrations=standing_integrations,
        )
        stop = Event()
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
        signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
        worker.run(stop, interval_seconds=interval)


def build_worker(
    runtime: Routine,
    projections: Projections,
    *,
    pack_root: Path,
    routine_revisions: tuple[RoutineRevision, ...] | None = None,
    fixed_operations: FixedOperations | None = None,
    synthetic_handler: _SyntheticHandler | None = None,
    durability_finalizer: DurabilityFinalizer | None = None,
    durability_progress: _DurabilityProgressRecorder | None = None,
    standing_integrations: tuple[_StandingIntegration, ...] = (),
) -> ControlWorker:
    """Compose the same worker around public kernel Interfaces."""

    revisions = (
        load_routine_revisions(pack_root) if routine_revisions is None else routine_revisions
    )
    return ControlWorker(
        runtime,
        RoutineLoop(runtime, revisions),
        OutboxLoop(projections),
        ProjectDeliveryLoop(projections),
        durability_finalizer,
        durability_progress,
        fixed_operations,
        synthetic_handler,
        standing_integrations,
    )


def _required_environment(key: str) -> str:
    value = os.environ.get(key)
    if value is None or not value.strip():
        raise RuntimeError(f"{key} must name a configured connection reference")
    return value


def _required_uuid(key: str) -> UUID:
    value = _required_environment(key)
    try:
        return UUID(value)
    except ValueError as error:
        raise RuntimeError(f"{key} must be a UUID") from error


def _required_digest(key: str) -> str:
    value = _required_environment(key)
    hex_digest = value[len(_DIGEST_PREFIX) :]
    if (
        not value.startswith(_DIGEST_PREFIX)
        or len(hex_digest) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in hex_digest)
    ):
        raise RuntimeError(f"{key} must be a lowercase sha256 digest")
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
