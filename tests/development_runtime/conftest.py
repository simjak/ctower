"""Disposable PostgreSQL fixtures for development-runtime integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from modules.migration._postgres import Database, isolated_database

from development_runtime._disposable_instance import DisposableInstance, disposable_cluster

__all__: tuple[str, ...] = ()


@pytest.fixture
def migration_database() -> Iterator[Database]:
    """Provide one real independently migrated PostgreSQL 17 database."""

    yield from isolated_database()


@pytest.fixture
def disposable_instance() -> Iterator[DisposableInstance]:
    """Provide one migrated throwaway cluster the checkpoint verbs may destroy."""

    yield from disposable_cluster()
