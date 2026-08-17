"""Background accepted-outbox projection loop."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ctower_kernel.projections import ProjectionMaintenanceResult, Projections

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutboxLoop:
    """Advance only accepted projection partitions outside request handling."""

    projections: Projections

    def tick(self, tenant_ids: tuple[UUID, ...]) -> tuple[ProjectionMaintenanceResult, ...]:
        return tuple(self.projections.catch_up(tenant_id) for tenant_id in tenant_ids)
