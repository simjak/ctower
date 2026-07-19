"""Real Postgres fixtures for Increment-1 acceptance."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from support.postgres import (
    DatabaseFixture,
    create_database,
    drop_database,
    start_postgres,
    stop_postgres,
)
from support.tenant_fixture import TenantFixture, create_first_tenant, create_second_tenant

__all__: tuple[str, ...] = ()


@pytest.fixture(scope="session", autouse=True)
def postgres_17() -> Iterator[None]:
    """Own the lifecycle of the authored development database composition."""

    start_postgres()
    yield
    stop_postgres()


@pytest.fixture
def database(postgres_17: None) -> Iterator[DatabaseFixture]:
    """Give each acceptance test an independently migrated database."""

    del postgres_17
    fixture = create_database()
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
