"""Project Delivery reconciliation inside the existing control worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ctower_kernel.projections import Projections

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectDeliveryLoop:
    """Reconcile event changes immediately and freshness only when due."""

    projections: Projections
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def tick(self, tenant_ids: tuple[UUID, ...]) -> tuple[int, ...]:
        now = self.clock()
        return tuple(
            self.projections.reconcile_project_delivery(tenant_id, now=now)
            for tenant_id in tenant_ids
        )
