"""Adversarial adoption evidence for the projection runtime login role."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from support.postgres import DatabaseFixture, PostgresServer, suspend_postgres_backend

from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

__all__: tuple[str, ...] = ()


def test_unsafe_preexisting_projection_role_is_quarantined_before_reuse(
    database: DatabaseFixture,
) -> None:
    escape_role = f"ctower_projection_escape_{database.name.removeprefix('ctower_test_')[:12]}"
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    active_login: psycopg.Connection[Any] | None = None
    other_login: psycopg.Connection[Any] | None = None
    try:
        _make_projection_role_unsafe(database.admin_dsn, escape_role)
        active_login = psycopg.connect(database.projection_dsn, autocommit=True)
        other_login = psycopg.connect(database.runtime_dsn, autocommit=True)
        active_login.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(escape_role)))
        active_login.execute("SET ROLE ctower_svc")
        active_login.execute("RESET ROLE")
        active_login.execute("SELECT 1 FROM tickets LIMIT 1")

        with pytest.raises(ValueError, match="unsafe pre-existing ctower_projection_runtime"):
            provision_database_roles(database.admin_dsn)

        with pytest.raises(psycopg.OperationalError):
            active_login.execute("SELECT 1")
        assert other_login.execute("SELECT 1").fetchone() == (1,)
        _assert_unsafe_role_quarantined(database)
    finally:
        if active_login is not None:
            active_login.close()
        if other_login is not None:
            other_login.close()
        _restore_projection_role(database.admin_dsn, escape_role)
        provision_database_roles(database.admin_dsn)


def test_quarantine_timeout_keeps_login_disabled_and_other_sessions_alive(
    database: DatabaseFixture, postgres_17: PostgresServer
) -> None:
    provision_database_roles(database.admin_dsn)
    hostile = psycopg.connect(database.projection_dsn, autocommit=True, row_factory=dict_row)
    other_login = psycopg.connect(database.runtime_dsn, autocommit=True)
    hostile_pid = _backend_pid(hostile)
    try:
        with suspend_postgres_backend(postgres_17, hostile_pid):
            with pytest.raises(RuntimeError, match="termination was not confirmed"):
                provision_database_roles(database.admin_dsn)

            with psycopg.connect(database.admin_dsn, row_factory=dict_row) as connection:
                role = connection.execute(
                    "SELECT rolcanlogin FROM pg_roles WHERE rolname = %s",
                    ("ctower_projection_runtime",),
                ).fetchone()
                sessions = connection.execute(
                    "SELECT pid FROM pg_stat_activity WHERE usename = %s ORDER BY pid",
                    ("ctower_projection_runtime",),
                ).fetchall()
            assert role == {"rolcanlogin": False}
            assert sessions == [{"pid": hostile_pid}]
            with pytest.raises(psycopg.OperationalError):
                psycopg.connect(database.projection_dsn, connect_timeout=1)
            assert other_login.execute("SELECT 1").fetchone() == (1,)
    finally:
        hostile.close()
        other_login.close()
        provision_database_roles(database.admin_dsn)


def _backend_pid(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()
    assert row is not None
    pid = row["pid"]
    assert isinstance(pid, int)
    return pid


def _assert_unsafe_role_quarantined(database: DatabaseFixture) -> None:
    with psycopg.connect(database.admin_dsn, row_factory=dict_row) as connection:
        role = connection.execute(
            """
            SELECT rolcanlogin, rolreplication, rolbypassrls,
                pg_has_role('ctower_projection_runtime', 'ctower_svc', 'MEMBER')
                    AS nested_service_membership,
                has_table_privilege('ctower_projection_runtime', 'tickets', 'SELECT')
                    AS direct_record_select
            FROM pg_roles WHERE rolname = 'ctower_projection_runtime'
            """
        ).fetchone()
        sessions = connection.execute(
            "SELECT pid FROM pg_stat_activity WHERE usename = %s",
            ("ctower_projection_runtime",),
        ).fetchall()
    assert role == {
        "rolcanlogin": False,
        "rolreplication": True,
        "rolbypassrls": True,
        "nested_service_membership": True,
        "direct_record_select": True,
    }
    assert sessions == []
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(database.projection_dsn, connect_timeout=1)


def _make_projection_role_unsafe(dsn: str, escape_role: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(escape_role)))
        connection.execute(sql.SQL("GRANT ctower_svc TO {}").format(sql.Identifier(escape_role)))
        connection.execute(
            sql.SQL("GRANT {} TO ctower_projection_runtime").format(sql.Identifier(escape_role))
        )
        connection.execute("ALTER ROLE ctower_projection_runtime REPLICATION BYPASSRLS")
        connection.execute("GRANT SELECT ON tickets TO ctower_projection_runtime")


def _restore_projection_role(dsn: str, escape_role: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("REVOKE SELECT ON tickets FROM ctower_projection_runtime")
        connection.execute(
            sql.SQL("REVOKE {} FROM ctower_projection_runtime").format(sql.Identifier(escape_role))
        )
        connection.execute(sql.SQL("REVOKE ctower_svc FROM {}").format(sql.Identifier(escape_role)))
        connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(escape_role)))
        connection.execute(
            """
            ALTER ROLE ctower_projection_runtime
                NOLOGIN NOREPLICATION NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            """
        )
