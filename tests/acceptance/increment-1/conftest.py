"""Real Postgres fixtures for Increment-1 acceptance."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from support.postgres import (
    DatabaseFixture,
    PostgresServer,
    create_database,
    drop_database,
    start_postgres,
    stop_postgres,
)
from support.tenant_fixture import TenantFixture, create_first_tenant, create_second_tenant

__all__: tuple[str, ...] = ()


@pytest.fixture(scope="session", autouse=True)
def postgres_17() -> Iterator[PostgresServer]:
    """Own the lifecycle of the authored development database composition."""

    server = start_postgres()
    yield server
    stop_postgres(server)


@pytest.fixture
def database(postgres_17: PostgresServer) -> Iterator[DatabaseFixture]:
    """Give each acceptance test an independently migrated database."""

    fixture = create_database(postgres_17)
    yield fixture
    drop_database(fixture)


@pytest.fixture
def tenant(database: DatabaseFixture) -> TenantFixture:
    """Provide one authenticated, bootstrap-created tenant."""

    return create_first_tenant(database)


@pytest.fixture
def second_tenant(tenant: TenantFixture) -> TenantFixture:
    """Add one real setup-only tenant administrator beside the bootstrap tenant."""

    return create_second_tenant(tenant.database)
