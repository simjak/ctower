"""Health projection acceptance evidence for the deterministic CP3-B control loop."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.projections import (
    HealthContributorKey,
    HealthStatus,
    Projections,
)
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import (
    Actor,
    DurabilityHealth,
    DurabilityHealthStatus,
    PrincipalKind,
)
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

_HTTP_OK = 200


def test_health_keeps_future_contributors_explicitly_unknown(tenant: TenantFixture) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    now = datetime.now(UTC)
    snapshot = Projections(PostgresProjections(tenant.database.projection_dsn)).health(
        actor,
        DurabilityHealth(
            DurabilityHealthStatus.HEALTHY,
            "ctower.test-acceptance@1",
            "ctower-test-standby",
            1,
            now,
            "current",
        ),
        now=now,
    )
    contributors = {
        item.key: item
        for dimension in (snapshot.availability, snapshot.completeness, snapshot.integrity)
        for item in dimension.contributors
    }

    assert set(contributors) == set(HealthContributorKey)
    for key in (
        HealthContributorKey.BACKUP,
        HealthContributorKey.ANCHOR,
        HealthContributorKey.OBJECT,
        HealthContributorKey.SYNTHETIC,
    ):
        assert contributors[key].status is HealthStatus.STATE_UNKNOWN
        assert contributors[key].watermark is None
        assert contributors[key].reason == "not-applicable-in-cp3-b"
    assert snapshot.status is HealthStatus.STATE_UNKNOWN

    command_id = uuid4()
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
    )
    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(command_id),
            },
        )
    assert response.status_code == _HTTP_OK
    assert response.json()["schema_id"] == "ctower.health/v1"
