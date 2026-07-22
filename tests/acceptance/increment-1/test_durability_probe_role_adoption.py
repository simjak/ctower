"""Adversarial upgrade evidence for durability-probe role adoption."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from support.postgres import DatabaseFixture

from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

__all__: tuple[str, ...] = ()

_ATTACKER = "ctower_probe_upgrade_attacker"
_PROBE = "ctower_durability_probe"


def test_unsafe_preexisting_probe_role_is_quarantined_before_reuse(
    database: DatabaseFixture,
) -> None:
    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    _seed_unsafe_probe(database.admin_dsn)
    attacker: psycopg.Connection[Any] | None = None
    direct_probe: psycopg.Connection[Any] | None = None
    try:
        attacker = psycopg.connect(_role_dsn(database.admin_dsn, _ATTACKER), autocommit=True)
        attacker.execute(f"SET ROLE {_PROBE}")
        direct_probe = psycopg.connect(_role_dsn(database.admin_dsn, _PROBE), autocommit=True)

        with pytest.raises(ValueError, match="health function boundary"):
            provision_database_roles(database.admin_dsn)

        with pytest.raises(psycopg.OperationalError):
            attacker.execute("SELECT 1")
        with pytest.raises(psycopg.OperationalError):
            direct_probe.execute("SELECT 1")
        _assert_quarantined(database.admin_dsn)
    finally:
        if attacker is not None:
            attacker.close()
        if direct_probe is not None:
            direct_probe.close()
        _remove_unsafe_probe_state(database.admin_dsn)

    provision_database_roles(database.admin_dsn)
    _assert_exact_probe_boundary(database.admin_dsn)


def _seed_unsafe_probe(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(f"CREATE ROLE {_ATTACKER} LOGIN")
        connection.execute(f"GRANT {_PROBE} TO {_ATTACKER} WITH INHERIT FALSE, SET TRUE")
        connection.execute(f"GRANT ctower_svc TO {_PROBE} WITH INHERIT TRUE, SET TRUE")
        connection.execute(f"ALTER ROLE {_PROBE} LOGIN REPLICATION BYPASSRLS")
        connection.execute(f"ALTER ROLE {_PROBE} SET search_path = attacker, public")
        connection.execute(f"GRANT CREATE ON SCHEMA public TO {_PROBE}")
        connection.execute(f"GRANT SELECT ON durability_policy_state TO {_PROBE}")
        connection.execute(
            f"GRANT EXECUTE ON FUNCTION durability_primary_live_evidence() TO {_ATTACKER}"
        )
        connection.execute(
            """
            CREATE FUNCTION probe_upgrade_hijack() RETURNS integer
            LANGUAGE sql AS $$ SELECT 1 $$
            """
        )
        connection.execute(f"ALTER FUNCTION probe_upgrade_hijack() OWNER TO {_PROBE}")
        connection.execute(f"SET ROLE {_PROBE}")
        connection.execute(_FORGED_PRIMARY_PROBE)
        connection.execute("RESET ROLE")


def _assert_quarantined(dsn: str) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        state = connection.execute(
            """
            SELECT role.rolcanlogin, role.rolreplication, role.rolbypassrls,
                EXISTS (
                    SELECT 1 FROM pg_auth_members AS membership
                    JOIN pg_roles AS member ON member.oid = membership.member
                    WHERE membership.roleid = role.oid AND member.rolname = %s
                ) AS attacker_can_assume,
                pg_has_role(%s, 'ctower_svc', 'MEMBER') AS unsafe_outgoing,
                EXISTS (
                    SELECT 1 FROM pg_db_role_setting WHERE setrole = role.oid
                ) AS has_settings,
                has_function_privilege(
                    %s, 'durability_primary_live_evidence()', 'EXECUTE'
                ) AS attacker_can_execute,
                has_function_privilege(
                    'ctower_svc', 'durability_primary_live_evidence()', 'EXECUTE'
                ) AS service_can_execute
            FROM pg_roles AS role WHERE role.rolname = %s
            """,
            (_ATTACKER, _PROBE, _ATTACKER, _PROBE),
        ).fetchone()
        sessions = connection.execute(
            "SELECT usename FROM pg_stat_activity WHERE usename = ANY(%s)",
            ([_ATTACKER, _PROBE],),
        ).fetchall()
    assert state == {
        "rolcanlogin": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "attacker_can_assume": False,
        "unsafe_outgoing": False,
        "has_settings": False,
        "attacker_can_execute": False,
        "service_can_execute": False,
    }
    assert sessions == []


def _remove_unsafe_probe_state(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL("REVOKE SELECT ON durability_policy_state FROM {}").format(
                sql.Identifier(_PROBE)
            )
        )
        connection.execute("ALTER FUNCTION probe_upgrade_hijack() OWNER TO postgres")
        connection.execute("DROP FUNCTION probe_upgrade_hijack()")
        connection.execute(f"REVOKE {_PROBE} FROM {_ATTACKER}")
        connection.execute(f"REVOKE ctower_svc FROM {_PROBE}")
        connection.execute(f"ALTER ROLE {_PROBE} RESET ALL")
        connection.execute(
            f"ALTER ROLE {_PROBE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "INHERIT NOREPLICATION NOBYPASSRLS"
        )
        connection.execute(_REAL_PRIMARY_PROBE)
        connection.execute(f"DROP ROLE {_ATTACKER}")


def _assert_exact_probe_boundary(dsn: str) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        role = connection.execute(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                rolreplication, rolbypassrls
            FROM pg_roles WHERE rolname = %s
            """,
            (_PROBE,),
        ).fetchone()
        memberships = connection.execute(
            """
            SELECT granted.rolname AS granted_role, member.rolname AS member_role,
                membership.admin_option, membership.inherit_option, membership.set_option
            FROM pg_auth_members AS membership
            JOIN pg_roles AS granted ON granted.oid = membership.roleid
            JOIN pg_roles AS member ON member.oid = membership.member
            WHERE granted.rolname = %s OR member.rolname = %s
            ORDER BY granted.rolname, member.rolname
            """,
            (_PROBE, _PROBE),
        ).fetchall()
        functions = connection.execute(
            """
            SELECT procedure.proname, owner.rolname AS owner, procedure.prosecdef,
                procedure.proconfig, procedure.proacl,
                EXISTS (
                    SELECT 1
                    FROM aclexplode(coalesce(
                        procedure.proacl, acldefault('f', procedure.proowner)
                    )) AS privilege
                    WHERE privilege.grantee = 0
                      AND privilege.privilege_type = 'EXECUTE'
                ) AS public_execute,
                EXISTS (
                    SELECT 1
                    FROM aclexplode(coalesce(
                        procedure.proacl, acldefault('f', procedure.proowner)
                    )) AS privilege
                    JOIN pg_roles AS grantee ON grantee.oid = privilege.grantee
                    WHERE grantee.rolname = 'ctower_svc'
                      AND privilege.privilege_type = 'EXECUTE'
                ) AS service_execute
            FROM pg_proc AS procedure
            JOIN pg_roles AS owner ON owner.oid = procedure.proowner
            WHERE procedure.proname IN (
                'durability_primary_live_evidence',
                'durability_standby_live_evidence'
            )
            ORDER BY procedure.proname
            """
        ).fetchall()
        schema_privileges = connection.execute(
            """
            SELECT has_schema_privilege(%s, 'public', 'USAGE') AS usage,
                has_schema_privilege(%s, 'public', 'CREATE') AS create
            """,
            (_PROBE, _PROBE),
        ).fetchone()
        settings = connection.execute(
            """
            SELECT count(*) AS value FROM pg_db_role_setting
            WHERE setrole = (SELECT oid FROM pg_roles WHERE rolname = %s)
            """,
            (_PROBE,),
        ).fetchone()
    assert role == {
        "rolcanlogin": False,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolinherit": True,
        "rolreplication": False,
        "rolbypassrls": False,
    }
    assert memberships == [
        {
            "granted_role": "pg_read_all_stats",
            "member_role": "ctower_durability_probe",
            "admin_option": False,
            "inherit_option": True,
            "set_option": True,
        },
    ]
    assert [(row["owner"], row["prosecdef"], row["proconfig"]) for row in functions] == [
        (_PROBE, True, ["search_path=pg_catalog"]),
        (_PROBE, True, ["search_path=pg_catalog"]),
    ]
    assert [row["public_execute"] for row in functions] == [False, False], functions
    assert all(row["service_execute"] is True for row in functions)
    assert schema_privileges == {"usage": True, "create": False}
    assert settings == {"value": 0}
    for role_name in ("ctower_admin", "ctower_svc", "ctower_runtime", "ctower_projection"):
        with psycopg.connect(dsn, autocommit=True) as runtime:
            runtime.execute(f"SET SESSION AUTHORIZATION {role_name}")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                runtime.execute(f"SET ROLE {_PROBE}")


def _role_dsn(dsn: str, role: str) -> str:
    return dsn.replace("postgresql://postgres@", f"postgresql://{role}@", 1)


_PRIMARY_PROBE_SIGNATURE = """
CREATE OR REPLACE FUNCTION durability_primary_live_evidence()
RETURNS TABLE (
    matching_sender_count bigint,
    application_name text,
    replication_state text,
    sync_state text,
    replay_lsn pg_lsn,
    primary_flush_lsn pg_lsn,
    system_identifier numeric,
    timeline_id integer,
    synchronous_standby_names text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$ {body} $$
"""
_FORGED_PRIMARY_PROBE = _PRIMARY_PROBE_SIGNATURE.format(
    body="""
    SELECT 1::bigint, 'ctower_i1_ack'::text, 'streaming'::text, 'sync'::text,
        'FFFFFFFF/FFFFFFFF'::pg_lsn, '0/0'::pg_lsn, 1::numeric, 1::integer,
        'FIRST 1 (ctower_i1_ack)'::text
    """
)
_REAL_PRIMARY_PROBE = _PRIMARY_PROBE_SIGNATURE.format(
    body="""
    SELECT
        count(*) AS matching_sender_count,
        min(sender.application_name) AS application_name,
        min(sender.state) AS replication_state,
        min(sender.sync_state) AS sync_state,
        min(sender.replay_lsn::text)::pg_lsn AS replay_lsn,
        pg_current_wal_flush_lsn() AS primary_flush_lsn,
        (pg_control_system()).system_identifier,
        (pg_control_checkpoint()).timeline_id,
        current_setting('synchronous_standby_names') AS synchronous_standby_names
    FROM pg_stat_replication AS sender
    WHERE sender.application_name = 'ctower_i1_ack'
    """
)
