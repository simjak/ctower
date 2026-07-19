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
