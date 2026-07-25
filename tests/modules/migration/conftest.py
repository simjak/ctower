"""Focused PostgreSQL fixture without importing the currently stacked API lane."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ._postgres import Database, isolated_database

__all__: tuple[str, ...] = ()


@pytest.fixture(scope="module")
def migration_database() -> Iterator[Database]:
    yield from isolated_database()
