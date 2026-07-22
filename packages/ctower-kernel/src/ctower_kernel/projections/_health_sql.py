"""Typed fail-loud health composition from independent stored watermarks."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.projections import (
    ControlHealth,
    HealthContributor,
    HealthContributorKey,
    HealthDimension,
    HealthStatus,
)
from ctower_kernel.record import DurabilityHealth

__all__: tuple[str, ...] = ()
_FUTURE = frozenset(
    {
        HealthContributorKey.BACKUP,
        HealthContributorKey.ANCHOR,
        HealthContributorKey.OBJECT,
        HealthContributorKey.SYNTHETIC,
    }
)


def health(
    dsn: str,
    tenant_id: UUID,
    durability: DurabilityHealth,
    *,
    now: datetime,
) -> ControlHealth:
    """Never turn absent, stale, or deferred contributors into calm state."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        rows = connection.execute(
            "SELECT * FROM health_watermarks WHERE tenant_id = %s", (tenant_id,)
        ).fetchall()
    stored = {HealthContributorKey(str(row["contributor"])): row for row in rows}
    contributors = {
        key: _contributor(key, stored.get(key), durability, now) for key in HealthContributorKey
    }
    availability = _dimension((contributors[HealthContributorKey.DURABILITY],))
    completeness = _dimension(
        tuple(
            contributors[key]
            for key in (
                HealthContributorKey.SCHEDULER,
                HealthContributorKey.OUTBOX,
                HealthContributorKey.PROJECTION,
                HealthContributorKey.BACKUP,
                HealthContributorKey.OBJECT,
                HealthContributorKey.SYNTHETIC,
            )
        )
    )
    integrity = _dimension((contributors[HealthContributorKey.ANCHOR],))
    status = _status((availability.status, completeness.status, integrity.status))
    return ControlHealth(status, now, availability, completeness, integrity)


def _contributor(
    key: HealthContributorKey,
    row: dict[str, object] | None,
    durability: DurabilityHealth,
    now: datetime,
) -> HealthContributor:
    if key is HealthContributorKey.DURABILITY:
        return HealthContributor(
            key,
            HealthStatus(durability.status.value),
            durability.acceptance_position,
            60,
            durability.observed_at,
            "record",
            durability.reason,
        )
    if key in _FUTURE:
        return HealthContributor(
            key, HealthStatus.STATE_UNKNOWN, None, 0, now, key.value, "not-applicable-in-cp3-b"
        )
    if row is None:
        return HealthContributor(
            key, HealthStatus.STATE_UNKNOWN, None, 60, now, key.value, "not-observed"
        )
    observed = cast(datetime, row["observed_at"])
    threshold = int(cast(int, row["threshold_seconds"]))
    status = HealthStatus(str(row["status"]))
    reason = str(row["reason"])
    if (now - observed).total_seconds() > threshold:
        status = HealthStatus.STATE_UNKNOWN
        reason = f"stale:{reason}"
    return HealthContributor(
        key,
        status,
        cast(int | None, row["watermark"]),
        threshold,
        observed,
        str(row["owner"]),
        reason,
    )


def _dimension(contributors: tuple[HealthContributor, ...]) -> HealthDimension:
    return HealthDimension(_status(tuple(item.status for item in contributors)), contributors)


def _status(statuses: tuple[HealthStatus, ...]) -> HealthStatus:
    if HealthStatus.DEGRADED in statuses:
        return HealthStatus.DEGRADED
    if HealthStatus.STATE_UNKNOWN in statuses:
        return HealthStatus.STATE_UNKNOWN
    return HealthStatus.HEALTHY
