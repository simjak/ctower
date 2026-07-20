"""Collision-safe Compose lifecycle acceptance evidence."""

from __future__ import annotations

from typing import cast

import psycopg
from support.postgres import (
    DatabaseFixture,
    PostgresServer,
    create_database,
    drop_database,
    start_postgres,
    stop_postgres,
)

__all__: tuple[str, ...] = ()


def test_two_compose_fixtures_cannot_stop_or_read_each_other(
    postgres_17: PostgresServer,
) -> None:
    second = start_postgres()
    left: DatabaseFixture | None = None
    right: DatabaseFixture | None = None
    try:
        assert second.project != postgres_17.project
        assert second.port != postgres_17.port
        left = create_database(postgres_17)
        right = create_database(second)
        _write_marker(left.admin_dsn, "left")
        _write_marker(right.admin_dsn, "right")
        assert _read_marker(left.admin_dsn) == "left"
        assert _read_marker(right.admin_dsn) == "right"
    finally:
        if right is not None:
            drop_database(right)
        stop_postgres(second)

    assert left is not None
    assert _read_marker(left.admin_dsn) == "left"
    drop_database(left)


def _write_marker(dsn: str, value: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE TABLE fixture_marker (value text NOT NULL)")
        connection.execute("INSERT INTO fixture_marker (value) VALUES (%s)", (value,))


def _read_marker(dsn: str) -> str:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT value FROM fixture_marker").fetchone()
    if row is None:
        raise AssertionError("fixture marker disappeared")
    return str(cast(tuple[object, ...], row)[0])
