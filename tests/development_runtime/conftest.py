"""Disposable PostgreSQL fixtures for development-runtime integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from modules.migration._postgres import Database, isolated_database

__all__: tuple[str, ...] = ()


@pytest.fixture
def migration_database() -> Iterator[Database]:
    """Provide one real independently migrated PostgreSQL 17 database."""

    yield from isolated_database()
