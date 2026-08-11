"""Real-Postgres refusal proofs for unsafe Console reader-role adoption."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_kernel.record.postgres import MigrationExecutionError, provision_database_roles

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
    provision_database_roles(tenant.database.admin_dsn)
