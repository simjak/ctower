"""Real-Postgres refusal proofs for unsafe Console reader-role adoption."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NoReturn, cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from support.postgres import DatabaseFixture
from support.tenant_fixture import TenantFixture

from ctower_kernel.record.postgres import (
    MigrationBaseline,
    MigrationExecutionError,
    MigrationScript,
    apply_migrations,
    provision_database_roles,
)

__all__: tuple[str, ...] = ()


def test_console_output_reader_role_has_only_the_authored_custody_surface(
    tenant: TenantFixture,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        role = connection.execute(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                rolreplication, rolbypassrls, rolconnlimit
            FROM pg_roles WHERE rolname = 'console_output_reader'
            """
        ).fetchone()
        memberships = connection.execute(
            """
            SELECT member.rolname AS member_name, granted.rolname AS granted_name,
                membership.admin_option
            FROM pg_auth_members AS membership
            JOIN pg_roles AS member ON member.oid = membership.member
            JOIN pg_roles AS granted ON granted.oid = membership.roleid
            WHERE member.rolname = 'console_output_reader'
               OR granted.rolname = 'console_output_reader'
            ORDER BY member.rolname, granted.rolname
            """
        ).fetchall()
        settings = connection.execute(
            """
            SELECT 1 FROM pg_db_role_setting AS setting
            JOIN pg_roles AS role ON role.oid = setting.setrole
            WHERE role.rolname = 'console_output_reader'
            """
        ).fetchall()
        grants = connection.execute(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'console_output_reader'
            ORDER BY table_name, privilege_type
            """
        ).fetchall()
        schema_privileges = connection.execute(
            """
            SELECT
                has_schema_privilege('console_output_reader', 'public', 'USAGE') AS usage,
                has_schema_privilege('console_output_reader', 'public', 'CREATE') AS create
            """
        ).fetchone()
    assert role == {
        "rolcanlogin": False,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolinherit": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "rolconnlimit": -1,
    }
    assert memberships == [
        {
            "member_name": "ctower_admin",
            "granted_name": "console_output_reader",
            "admin_option": False,
        }
    ]
    assert settings == []
    assert [(row["table_name"], row["privilege_type"]) for row in grants] == [
        ("console_output_access_facts", "SELECT"),
        ("console_output_objects", "SELECT"),
        ("console_output_recovery_facts", "INSERT"),
    ]
    assert schema_privileges == {"usage": True, "create": False}
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_svc")
        connection.execute("SELECT ciphertext FROM console_output_objects LIMIT 1")
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE console_output_reader")


@pytest.mark.parametrize(
    ("object_kind", "object_name"),
    [("SCHEMA", "public"), ("TABLE", "console_output_objects")],
)
def test_console_output_reader_adoption_refuses_schema_or_table_ownership(
    tenant: TenantFixture,
    object_kind: str,
    object_name: str,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        owner = connection.execute(
            (
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = %s"
                if object_kind == "SCHEMA"
                else "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = %s::regclass"
            ),
            (object_name,),
        ).fetchone()
        assert owner is not None
        connection.execute(
            sql.SQL("ALTER {} {} OWNER TO console_output_reader").format(
                sql.SQL(object_kind), sql.Identifier(object_name)
            )
        )
    try:
        with pytest.raises(MigrationExecutionError, match="0064_console_output_reader_role"):
            provision_database_roles(tenant.database.admin_dsn)
    finally:
        with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("ALTER {} {} OWNER TO {}").format(
                    sql.SQL(object_kind),
                    sql.Identifier(object_name),
                    sql.Identifier(str(owner[0])),
                )
            )
            if object_kind == "SCHEMA":
                connection.execute("REVOKE ALL ON SCHEMA public FROM console_output_reader")
                connection.execute("GRANT USAGE ON SCHEMA public TO console_output_reader")
            else:
                connection.execute(
                    "REVOKE ALL ON console_output_objects FROM console_output_reader"
                )
                connection.execute(
                    "GRANT SELECT ON console_output_objects TO console_output_reader"
                )
    provision_database_roles(tenant.database.admin_dsn)


@pytest.mark.parametrize(
    "drift",
    ["table-delete", "table-grant-option", "column-select", "database-connect"],
)
def test_console_output_reader_adoption_refuses_every_extra_acl_edge(
    tenant: TenantFixture,
    drift: str,
) -> None:
    database_name = sql.Identifier(tenant.database.name)
    statements: dict[str, tuple[str | sql.Composed, str | sql.Composed]] = {
        "table-delete": (
            "GRANT DELETE ON console_output_objects TO console_output_reader",
            "REVOKE DELETE ON console_output_objects FROM console_output_reader",
        ),
        "table-grant-option": (
            "GRANT SELECT ON console_output_objects TO console_output_reader WITH GRANT OPTION",
            "REVOKE GRANT OPTION FOR SELECT ON console_output_objects FROM console_output_reader",
        ),
        "column-select": (
            "GRANT SELECT (access_id) ON console_output_recovery_facts TO console_output_reader",
            "REVOKE SELECT (access_id) ON console_output_recovery_facts FROM console_output_reader",
        ),
        "database-connect": (
            sql.SQL("GRANT CONNECT ON DATABASE {} TO console_output_reader").format(database_name),
            sql.SQL("REVOKE CONNECT ON DATABASE {} FROM console_output_reader").format(
                database_name
            ),
        ),
    }
    seed, cleanup = statements[drift]
    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        connection.execute(seed)
    try:
        with pytest.raises(MigrationExecutionError, match="0064_console_output_reader_role"):
            provision_database_roles(tenant.database.admin_dsn)
    finally:
        with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
            connection.execute(cleanup)
    provision_database_roles(tenant.database.admin_dsn)


def test_console_output_reader_adoption_refuses_shared_database_ownership(
    tenant: TenantFixture,
) -> None:
    database_name = sql.Identifier(tenant.database.name)
    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        owner = connection.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        assert owner is not None
        connection.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO console_output_reader").format(database_name)
        )
    try:
        with pytest.raises(MigrationExecutionError, match="0064_console_output_reader_role"):
            provision_database_roles(tenant.database.admin_dsn)
    finally:
        with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                    database_name, sql.Identifier(str(owner[0]))
                )
            )
    provision_database_roles(tenant.database.admin_dsn)


@pytest.mark.parametrize("failure_stage", ["after-grant", "after-schema-work"])
def test_console_reader_temporary_create_rolls_back_at_every_failure_boundary(
    database: DatabaseFixture,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: Literal["after-grant", "after-schema-work"],
) -> None:
    provision_database_roles(database.admin_dsn)
    apply_namespace = apply_migrations.__globals__
    original = cast(
        Callable[
            [
                psycopg.Connection[tuple[object, ...]],
                tuple[MigrationScript, ...],
                MigrationBaseline,
            ],
            object,
        ],
        apply_namespace["apply_database_migrations"],
    )

    def interrupt(
        connection: psycopg.Connection[tuple[object, ...]],
        migrations: tuple[MigrationScript, ...],
        baseline: MigrationBaseline,
    ) -> NoReturn:
        if failure_stage == "after-schema-work":
            original(connection, migrations, baseline)
        assert connection.execute(
            "SELECT has_schema_privilege('console_output_reader', 'public', 'CREATE')"
        ).fetchone() == (True,)
        raise RuntimeError("injected ownership-transfer interruption")

    monkeypatch.setitem(apply_namespace, "apply_database_migrations", interrupt)
    with pytest.raises(RuntimeError, match="ownership-transfer interruption"):
        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT has_schema_privilege('console_output_reader', 'public', 'CREATE')"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT to_regprocedure("
            "'public.recover_console_output_object(uuid,timestamp with time zone)')"
        ).fetchone() == (None,)

    monkeypatch.setitem(apply_namespace, "apply_database_migrations", original)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid = "
            "to_regprocedure('public.recover_console_output_object(uuid,timestamp with time zone)')"
        ).fetchone() == ("console_output_reader",)
        assert connection.execute(
            "SELECT has_schema_privilege('console_output_reader', 'public', 'CREATE')"
        ).fetchone() == (False,)
