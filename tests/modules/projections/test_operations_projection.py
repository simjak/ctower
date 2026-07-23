"""Operations projection values remain strict and independently attributable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from ctower_kernel.projections import (
    ControlHealth,
    HealthContributor,
    HealthContributorKey,
    HealthDimension,
    HealthStatus,
)


def test_control_health_preserves_each_contributor_without_flattening_dimensions() -> None:
    observed = datetime(2026, 7, 22, tzinfo=UTC)
    durability = HealthContributor(
        HealthContributorKey.DURABILITY,
        HealthStatus.HEALTHY,
        17,
        60,
        observed,
        "record",
        "accepted",
    )
    scheduler = HealthContributor(
        HealthContributorKey.SCHEDULER,
        HealthStatus.STATE_UNKNOWN,
        None,
        60,
        observed,
        "runtime",
        "not-scanned",
    )
    remainder = {
        key: HealthContributor(
            key,
            HealthStatus.STATE_UNKNOWN,
            None,
            60,
            observed,
            key.value,
            "not-observed",
        )
        for key in HealthContributorKey
        if key not in {HealthContributorKey.DURABILITY, HealthContributorKey.SCHEDULER}
    }
    health = ControlHealth(
        HealthStatus.STATE_UNKNOWN,
        observed,
        HealthDimension(HealthStatus.HEALTHY, (durability,)),
        HealthDimension(
            HealthStatus.STATE_UNKNOWN,
            (
                scheduler,
                remainder[HealthContributorKey.OUTBOX],
                remainder[HealthContributorKey.PROJECTION],
                remainder[HealthContributorKey.BACKUP],
                remainder[HealthContributorKey.OBJECT],
                remainder[HealthContributorKey.SYNTHETIC],
            ),
        ),
        HealthDimension(
            HealthStatus.STATE_UNKNOWN,
            (remainder[HealthContributorKey.ANCHOR],),
        ),
    )

    payload = health.response_payload()

    assert payload["status"] == "STATE_UNKNOWN"
    assert payload["availability"] == {
        "status": "HEALTHY",
        "contributors": [durability.response_payload()],
    }
    completeness = payload["completeness"]
    assert isinstance(completeness, dict)
    assert completeness["status"] == "STATE_UNKNOWN"
    assert cast(list[dict[str, object]], completeness["contributors"])[0] == (
        scheduler.response_payload()
    )
