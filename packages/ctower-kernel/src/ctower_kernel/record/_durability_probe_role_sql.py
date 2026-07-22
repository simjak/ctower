"""Fail-closed provisioning for the narrow durability evidence role."""

from __future__ import annotations

from typing import cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

__all__ = [
    "DURABILITY_PROBE_ROLE",
    "close_durability_probe_boundary",
    "probe_role_rejection_reasons",
    "quarantine_durability_probe",
]

DURABILITY_PROBE_ROLE = "ctower_durability_probe"
_SERVICE_ROLE = "ctower_svc"
_HEALTH_FUNCTIONS = (
    "durability_primary_live_evidence",
    "durability_standby_live_evidence",
)
_HEALTH_FUNCTION_BODIES = {
    "durability_primary_live_evidence": (
        "SELECT count(*) AS matching_sender_count, "
        "min(sender.application_name) AS application_name, "
        "min(sender.state) AS replication_state, min(sender.sync_state) AS sync_state, "
        "min(sender.replay_lsn::text)::pg_lsn AS replay_lsn, "
        "pg_current_wal_flush_lsn() AS primary_flush_lsn, "
        "(pg_control_system()).system_identifier, "
        "(pg_control_checkpoint()).timeline_id, "
        "current_setting('synchronous_standby_names') AS synchronous_standby_names "
        "FROM pg_stat_replication AS sender "
        "WHERE sender.application_name = 'ctower_i1_ack'"
    ),
    "durability_standby_live_evidence": (
        "SELECT count(*) AS matching_receiver_count, "
        "min(receiver.status) AS receiver_status, "
        "current_setting('cluster_name') AS cluster_name, "
        "pg_is_in_recovery() AS in_recovery, "
        "pg_is_wal_replay_paused() AS replay_paused, "
        "pg_last_wal_replay_lsn() AS replay_lsn, "
        "(pg_control_system()).system_identifier, "
        "(pg_control_checkpoint()).timeline_id FROM pg_stat_wal_receiver AS receiver"
    ),
}
_SESSION_TERMINATION_TIMEOUT_MS = 5_000


def quarantine_durability_probe(admin_dsn: str) -> bool:
    """Remove every active authority path before inspecting an existing role."""

    with psycopg.connect(admin_dsn, autocommit=True, row_factory=dict_row) as connection:
        role = connection.execute(
            "SELECT oid FROM pg_roles WHERE rolname = %s", (DURABILITY_PROBE_ROLE,)
        ).fetchone()
        if role is None:
            return False
        role_id = role["oid"]
        incoming = _incoming_role_names(connection, role_id)
        connection.execute(
            sql.SQL(
                "ALTER ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "INHERIT NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(DURABILITY_PROBE_ROLE))
        )
        _terminate_role_sessions(connection, incoming | {DURABILITY_PROBE_ROLE})
        _revoke_probe_memberships(connection, role_id)
        _reset_probe_settings(connection, role_id)
        connection.execute(
            sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(
                sql.Identifier(DURABILITY_PROBE_ROLE)
            )
        )
        _quarantine_health_function_acls(connection)
    return True


def close_durability_probe_boundary(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    """Close transient schema authority after the two probe functions exist."""

    if _owned_health_function_count(connection) != len(_HEALTH_FUNCTIONS):
        return
    connection.execute(
        sql.SQL("REVOKE USAGE, CREATE ON SCHEMA public FROM {}").format(
            sql.Identifier(DURABILITY_PROBE_ROLE)
        )
    )
    connection.execute(
        sql.SQL("REVOKE {} FROM {}").format(
            sql.Identifier(DURABILITY_PROBE_ROLE), sql.Identifier("ctower_admin")
        )
    )
    _quarantine_health_function_acls(connection)
    for function in _HEALTH_FUNCTIONS:
        connection.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION public.{}() TO {}").format(
                sql.Identifier(function), sql.Identifier(_SERVICE_ROLE)
            )
        )


def probe_role_rejection_reasons(
    connection: psycopg.Connection[dict[str, object]], *, provisioned: bool
) -> tuple[str, ...]:
    """Return exact-boundary differences after active paths have been quarantined."""

    role = connection.execute(
        """
        SELECT oid, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
            rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname = %s
        """,
        (DURABILITY_PROBE_ROLE,),
    ).fetchone()
    if role is None:
        return ("role is absent",)
    return (
        *_probe_attribute_rejections(role),
        *_probe_authority_rejections(connection, role["oid"], provisioned=provisioned),
    )


def _probe_attribute_rejections(role: dict[str, object]) -> tuple[str, ...]:
    actual_attributes = tuple(
        bool(role[name])
        for name in (
            "rolcanlogin",
            "rolsuper",
            "rolcreatedb",
            "rolcreaterole",
            "rolinherit",
            "rolreplication",
            "rolbypassrls",
        )
    )
    expected_attributes = (False, False, False, False, True, False, False)
    return () if actual_attributes == expected_attributes else ("role attributes",)


def _probe_authority_rejections(
    connection: psycopg.Connection[dict[str, object]],
    role_id: object,
    *,
    provisioned: bool,
) -> tuple[str, ...]:
    transient_memberships = {
        (DURABILITY_PROBE_ROLE, "ctower_admin", False, False, True),
        ("pg_read_all_stats", DURABILITY_PROBE_ROLE, False, True, True),
    }
    function_count = _owned_health_function_count(connection)
    closed_memberships = {("pg_read_all_stats", DURABILITY_PROBE_ROLE, False, True, True)}
    expected_memberships = transient_memberships if function_count == 0 else closed_memberships
    create_allowed = function_count == 0 and provisioned
    checks = (
        (
            "membership graph or options",
            _probe_memberships(connection, role_id)
            != (expected_memberships if provisioned else set()),
        ),
        ("role settings", _probe_has_settings(connection, role_id)),
        ("unexpected ownership", _unexpected_probe_ownership(connection, role_id)),
        ("direct table grants", _probe_has_direct_table_grants(connection)),
        (
            "health function boundary",
            bool(function_count)
            and _health_function_boundary_is_inexact(connection, require_service=provisioned),
        ),
        ("schema CREATE privilege", _probe_has_schema_create(connection) is not create_allowed),
    )
    return tuple(reason for reason, rejected in checks if rejected)


def _incoming_role_names(
    connection: psycopg.Connection[dict[str, object]], role_id: object
) -> set[str]:
    rows = connection.execute(
        """
        WITH RECURSIVE incoming(member) AS (
            SELECT membership.member FROM pg_auth_members AS membership
            WHERE membership.roleid = %s
            UNION
            SELECT membership.member FROM pg_auth_members AS membership
            JOIN incoming ON membership.roleid = incoming.member
        )
        SELECT role.rolname FROM incoming
        JOIN pg_roles AS role ON role.oid = incoming.member
        """,
        (role_id,),
    ).fetchall()
    return {str(row["rolname"]) for row in rows}


def _terminate_role_sessions(
    connection: psycopg.Connection[dict[str, object]], role_names: set[str]
) -> None:
    results = connection.execute(
        """
        SELECT pid, pg_catalog.pg_terminate_backend(pid, %s) AS terminated
        FROM pg_stat_activity
        WHERE usename = ANY(%s) AND pid <> pg_backend_pid()
        ORDER BY pid
        """,
        (_SESSION_TERMINATION_TIMEOUT_MS, sorted(role_names)),
    ).fetchall()
    if any(row["terminated"] is not True for row in results):
        raise RuntimeError(f"{DURABILITY_PROBE_ROLE} session termination was not confirmed")
    survivor = connection.execute(
        "SELECT 1 FROM pg_stat_activity "
        "WHERE usename = ANY(%s) AND pid <> pg_backend_pid() LIMIT 1",
        (sorted(role_names),),
    ).fetchone()
    if survivor is not None:
        raise RuntimeError(f"{DURABILITY_PROBE_ROLE} assumption session survived quarantine")


def _revoke_probe_memberships(
    connection: psycopg.Connection[dict[str, object]], role_id: object
) -> None:
    rows = connection.execute(
        """
        SELECT granted.rolname AS granted_role, member.rolname AS member_role
        FROM pg_auth_members AS membership
        JOIN pg_roles AS granted ON granted.oid = membership.roleid
        JOIN pg_roles AS member ON member.oid = membership.member
        WHERE membership.roleid = %s OR membership.member = %s
        """,
        (role_id, role_id),
    ).fetchall()
    for row in rows:
        connection.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(str(row["granted_role"])),
                sql.Identifier(str(row["member_role"])),
            )
        )


def _reset_probe_settings(
    connection: psycopg.Connection[dict[str, object]], role_id: object
) -> None:
    rows = connection.execute(
        """
        SELECT database.datname FROM pg_db_role_setting AS setting
        LEFT JOIN pg_database AS database ON database.oid = setting.setdatabase
        WHERE setting.setrole = %s
        """,
        (role_id,),
    ).fetchall()
    connection.execute(
        sql.SQL("ALTER ROLE {} RESET ALL").format(sql.Identifier(DURABILITY_PROBE_ROLE))
    )
    for row in rows:
        if row["datname"] is not None:
            connection.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} RESET ALL").format(
                    sql.Identifier(DURABILITY_PROBE_ROLE),
                    sql.Identifier(str(row["datname"])),
                )
            )


def _quarantine_health_function_acls(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    for function in _HEALTH_FUNCTIONS:
        identity = f"public.{function}()"
        function_row = connection.execute(
            "SELECT to_regprocedure(%s) AS value", (identity,)
        ).fetchone()
        if function_row is None or function_row["value"] is None:
            continue
        connection.execute(
            sql.SQL("REVOKE ALL ON FUNCTION public.{}() FROM PUBLIC").format(
                sql.Identifier(function)
            )
        )
        grantees = connection.execute(
            """
            SELECT DISTINCT grantee.rolname
            FROM pg_proc AS procedure
            CROSS JOIN LATERAL aclexplode(coalesce(
                procedure.proacl, acldefault('f', procedure.proowner)
            )) AS privilege
            JOIN pg_roles AS grantee ON grantee.oid = privilege.grantee
            WHERE procedure.oid = to_regprocedure(%s)
              AND grantee.rolname <> %s
            """,
            (identity, DURABILITY_PROBE_ROLE),
        ).fetchall()
        for grantee in grantees:
            connection.execute(
                sql.SQL("REVOKE ALL ON FUNCTION public.{}() FROM {}").format(
                    sql.Identifier(function), sql.Identifier(str(grantee["rolname"]))
                )
            )


def _probe_memberships(
    connection: psycopg.Connection[dict[str, object]], role_id: object
) -> set[tuple[str, str, bool, bool, bool]]:
    return {
        (
            str(row["granted_role"]),
            str(row["member_role"]),
            bool(row["admin_option"]),
            bool(row["inherit_option"]),
            bool(row["set_option"]),
        )
        for row in connection.execute(
            """
            SELECT granted.rolname AS granted_role, member.rolname AS member_role,
                membership.admin_option, membership.inherit_option, membership.set_option
            FROM pg_auth_members AS membership
            JOIN pg_roles AS granted ON granted.oid = membership.roleid
            JOIN pg_roles AS member ON member.oid = membership.member
            WHERE membership.roleid = %s OR membership.member = %s
            """,
            (role_id, role_id),
        ).fetchall()
    }


def _probe_has_settings(connection: psycopg.Connection[dict[str, object]], role_id: object) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM pg_db_role_setting WHERE setrole = %s LIMIT 1", (role_id,)
        ).fetchone()
        is not None
    )


def _unexpected_probe_ownership(
    connection: psycopg.Connection[dict[str, object]], role_id: object
) -> bool:
    functions = connection.execute(
        """
        SELECT namespace.nspname, procedure.proname,
            pg_get_function_identity_arguments(procedure.oid) AS arguments
        FROM pg_proc AS procedure
        JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
        WHERE procedure.proowner = %s
        """,
        (role_id,),
    ).fetchall()
    allowed = {("public", function, "") for function in _HEALTH_FUNCTIONS}
    actual = {
        (str(row["nspname"]), str(row["proname"]), str(row["arguments"])) for row in functions
    }
    if actual - allowed:
        return True
    return (
        connection.execute(
            "SELECT 1 FROM pg_class WHERE relowner = %s LIMIT 1", (role_id,)
        ).fetchone()
        is not None
    )


def _probe_has_direct_table_grants(
    connection: psycopg.Connection[dict[str, object]],
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM information_schema.table_privileges WHERE grantee = %s LIMIT 1",
            (DURABILITY_PROBE_ROLE,),
        ).fetchone()
        is not None
    )


def _owned_health_function_count(
    connection: psycopg.Connection[dict[str, object]],
) -> int:
    row = connection.execute(
        """
        SELECT count(*) AS value FROM pg_proc AS procedure
        JOIN pg_roles AS owner ON owner.oid = procedure.proowner
        WHERE owner.rolname = %s AND procedure.proname = ANY(%s)
          AND pg_get_function_identity_arguments(procedure.oid) = ''
        """,
        (DURABILITY_PROBE_ROLE, list(_HEALTH_FUNCTIONS)),
    ).fetchone()
    return 0 if row is None else int(cast(int, row["value"]))


def _health_function_boundary_is_inexact(
    connection: psycopg.Connection[dict[str, object]],
    *,
    require_service: bool,
) -> bool:
    rows = connection.execute(
        """
        SELECT procedure.proname, owner.rolname AS owner, language.lanname,
            procedure.prosecdef, procedure.proconfig, procedure.prosrc,
            pg_get_function_identity_arguments(procedure.oid) AS arguments
        FROM pg_proc AS procedure
        JOIN pg_roles AS owner ON owner.oid = procedure.proowner
        JOIN pg_language AS language ON language.oid = procedure.prolang
        WHERE procedure.oid = ANY(ARRAY[
            to_regprocedure('public.durability_primary_live_evidence()'),
            to_regprocedure('public.durability_standby_live_evidence()')
        ])
        ORDER BY procedure.proname
        """
    ).fetchall()
    expected = [
        (
            function,
            DURABILITY_PROBE_ROLE,
            "sql",
            True,
            ["search_path=pg_catalog, pg_temp"],
            "",
            _HEALTH_FUNCTION_BODIES[function],
        )
        for function in _HEALTH_FUNCTIONS
    ]
    actual = [
        (
            str(row["proname"]),
            str(row["owner"]),
            str(row["lanname"]),
            bool(row["prosecdef"]),
            row["proconfig"],
            str(row["arguments"]),
            " ".join(str(row["prosrc"]).split()),
        )
        for row in rows
    ]
    if actual != expected:
        return True
    privileges = connection.execute(
        """
        SELECT procedure.proname, coalesce(grantee.rolname, 'PUBLIC') AS grantee,
            privilege.privilege_type, privilege.is_grantable
        FROM pg_proc AS procedure
        CROSS JOIN LATERAL aclexplode(coalesce(
            procedure.proacl, acldefault('f', procedure.proowner)
        )) AS privilege
        LEFT JOIN pg_roles AS grantee ON grantee.oid = privilege.grantee
        WHERE procedure.oid = ANY(ARRAY[
            to_regprocedure('public.durability_primary_live_evidence()'),
            to_regprocedure('public.durability_standby_live_evidence()')
        ])
        ORDER BY procedure.proname, grantee
        """
    ).fetchall()
    owner_privileges = {
        (function, DURABILITY_PROBE_ROLE, "EXECUTE", False) for function in _HEALTH_FUNCTIONS
    }
    service_privileges = {
        (function, _SERVICE_ROLE, "EXECUTE", False) for function in _HEALTH_FUNCTIONS
    }
    expected_privileges = owner_privileges | service_privileges
    actual_privileges = {
        (
            str(row["proname"]),
            str(row["grantee"]),
            str(row["privilege_type"]),
            bool(row["is_grantable"]),
        )
        for row in privileges
    }
    return actual_privileges != (expected_privileges if require_service else owner_privileges)


def _probe_has_schema_create(
    connection: psycopg.Connection[dict[str, object]],
) -> bool:
    row = connection.execute(
        "SELECT has_schema_privilege(%s, 'public', 'CREATE') AS value",
        (DURABILITY_PROBE_ROLE,),
    ).fetchone()
    return row is not None and row["value"] is True
