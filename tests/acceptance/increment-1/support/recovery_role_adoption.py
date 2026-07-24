"""Adversarial reusable-role catalog cases for the recovery boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql
from support.postgres import (
    DatabaseFixture,
    create_database,
    drop_database,
    start_postgres,
    stop_postgres,
)

from ctower_kernel.record.postgres import (
    RecoveryRoleConfigurationError,
    apply_migrations,
    provision_database_roles,
)

__all__ = [
    "RECOVERY_ROLES",
    "assert_clean_creation_and_exact_reuse",
    "assert_mismatch_cases_are_atomic",
]

RECOVERY_ROLES = (
    "ctower_object",
    "ctower_backup",
    "ctower_anchor",
    "ctower_restore",
)
_SANITIZED_ERROR = "recovery role configuration does not match the declared catalog shape"


@dataclass(frozen=True, slots=True)
class _MismatchCase:
    name: str
    seed: Callable[[psycopg.Connection[tuple[object, ...]], str, DatabaseFixture], None]
    cleanup: Callable[[psycopg.Connection[tuple[object, ...]], str, DatabaseFixture], None]


def assert_clean_creation_and_exact_reuse() -> None:
    """Prove malformed adoption is atomic before proving both exact reuse phases."""

    server = start_postgres()
    database = create_database(server)
    try:
        with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
            connection.execute("CREATE ROLE ctower_restore LOGIN NOINHERIT")
        before = _catalog_snapshot(database.admin_dsn)
        _assert_deterministic_rejection(database, before)
        assert _existing_recovery_roles(database.admin_dsn) == ("ctower_restore",)

        with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
            connection.execute("DROP ROLE ctower_restore")
            connection.execute("CREATE TABLE backup_manifests (marker integer)")
        before = _catalog_snapshot(database.admin_dsn)
        _assert_deterministic_rejection(database, before)
        assert _existing_recovery_roles(database.admin_dsn) == ()
        with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
            connection.execute("DROP TABLE backup_manifests")

        provision_database_roles(database.admin_dsn)
        empty_shape = _catalog_snapshot(database.admin_dsn)
        provision_database_roles(database.admin_dsn)
        assert _catalog_snapshot(database.admin_dsn) == empty_shape

        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
        provisioned_shape = _catalog_snapshot(database.admin_dsn)
        provision_database_roles(database.admin_dsn)
        provision_database_roles(database.admin_dsn)
        assert _catalog_snapshot(database.admin_dsn) == provisioned_shape
    finally:
        drop_database(database)
        stop_postgres(server)


def assert_mismatch_cases_are_atomic(database: DatabaseFixture, role: str) -> None:
    """Reject every mismatch twice without changing its catalog fingerprint."""

    provision_database_roles(database.admin_dsn)
    apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)
    for case in _mismatch_cases():
        with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
            case.seed(connection, role, database)
        before = _catalog_snapshot(database.admin_dsn)
        _assert_deterministic_rejection(database, before)
        with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
            case.cleanup(connection, role, database)
        provision_database_roles(database.admin_dsn)


def _assert_deterministic_rejection(
    database: DatabaseFixture,
    before: tuple[tuple[tuple[object, ...], ...], ...],
) -> None:
    messages: list[str] = []
    for _ in range(2):
        with pytest.raises(RecoveryRoleConfigurationError) as raised:
            provision_database_roles(database.admin_dsn)
        messages.append(str(raised.value))
        assert _catalog_snapshot(database.admin_dsn) == before
    assert messages == [_SANITIZED_ERROR, _SANITIZED_ERROR]


def _catalog_snapshot(dsn: str) -> tuple[tuple[tuple[object, ...], ...], ...]:
    queries = (
        """
        SELECT oid, rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
            rolinherit, rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname
        """,
        """
        SELECT roleid, member, grantor, admin_option, inherit_option, set_option
        FROM pg_auth_members
        WHERE roleid IN (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
           OR member IN (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
        ORDER BY roleid, member, grantor
        """,
        """
        SELECT setdatabase, setrole, setconfig
        FROM pg_db_role_setting
        WHERE setrole IN (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
        ORDER BY setdatabase, setrole
        """,
        """
        SELECT dbid, classid, objid, objsubid, refclassid, refobjid, deptype
        FROM pg_shdepend
        WHERE refclassid = 'pg_authid'::regclass
          AND refobjid IN (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
        ORDER BY dbid, classid, objid, objsubid, refobjid, deptype
        """,
    )
    with psycopg.connect(dsn) as connection:
        roles = tuple(connection.execute(queries[0], (list(RECOVERY_ROLES),)).fetchall())
        memberships = tuple(
            connection.execute(queries[1], (list(RECOVERY_ROLES), list(RECOVERY_ROLES))).fetchall()
        )
        settings = tuple(connection.execute(queries[2], (list(RECOVERY_ROLES),)).fetchall())
        dependencies = tuple(connection.execute(queries[3], (list(RECOVERY_ROLES),)).fetchall())
    return roles, memberships, settings, dependencies


def _existing_recovery_roles(dsn: str) -> tuple[str, ...]:
    with psycopg.connect(dsn) as connection:
        return tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
                (list(RECOVERY_ROLES),),
            ).fetchall()
        )


def _mismatch_cases() -> tuple[_MismatchCase, ...]:
    attributes = tuple(
        _MismatchCase(name, _attribute_mutation(enabled), _attribute_mutation(disabled))
        for name, enabled, disabled in (
            ("login", "LOGIN", "NOLOGIN"),
            ("inherit", "INHERIT", "NOINHERIT"),
            ("create-role", "CREATEROLE", "NOCREATEROLE"),
            ("create-db", "CREATEDB", "NOCREATEDB"),
            ("replication", "REPLICATION", "NOREPLICATION"),
            ("bypass-rls", "BYPASSRLS", "NOBYPASSRLS"),
            ("superuser", "SUPERUSER", "NOSUPERUSER"),
        )
    )
    return (
        *attributes,
        _MismatchCase("outgoing-membership", _seed_outgoing_membership, _drop_bridge),
        _MismatchCase("incoming-membership", _seed_incoming_membership, _drop_bridge),
        _MismatchCase("global-setting", _seed_global_setting, _reset_global_setting),
        _MismatchCase("database-setting", _seed_database_setting, _reset_database_setting),
        _MismatchCase("owned-object", _seed_owned_object, _drop_owned_object),
        _MismatchCase("object-grant", _seed_object_grant, _revoke_object_grant),
        _MismatchCase("database-grant", _seed_database_grant, _revoke_database_grant),
        _MismatchCase("schema-grant", _seed_schema_grant, _revoke_schema_grant),
        _MismatchCase("grant-option", _seed_grant_option, _revoke_grant_option),
        _MismatchCase("default-grant", _seed_default_grant, _revoke_default_grant),
    )


def _attribute_mutation(
    attribute: str,
) -> Callable[[psycopg.Connection[tuple[object, ...]], str, DatabaseFixture], None]:
    def mutate(
        connection: psycopg.Connection[tuple[object, ...]],
        role: str,
        _database: DatabaseFixture,
    ) -> None:
        connection.execute(
            sql.SQL("ALTER ROLE {} {}").format(sql.Identifier(role), sql.SQL(attribute))
        )

    return mutate


def _bridge(database: DatabaseFixture) -> str:
    return f"recovery_bridge_{database.name.removeprefix('ctower_test_')[:16]}"


def _seed_outgoing_membership(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    bridge = _bridge(database)
    connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(bridge)))
    connection.execute(sql.SQL("GRANT pg_read_all_data TO {}").format(sql.Identifier(bridge)))
    connection.execute(
        sql.SQL("GRANT {} TO {}").format(sql.Identifier(bridge), sql.Identifier(role))
    )


def _seed_incoming_membership(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    bridge = _bridge(database)
    connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(bridge)))
    connection.execute(
        sql.SQL("GRANT {} TO {}").format(sql.Identifier(role), sql.Identifier(bridge))
    )


def _drop_bridge(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    bridge = _bridge(database)
    connection.execute(
        sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(role), sql.Identifier(bridge))
    )
    connection.execute(
        sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(bridge), sql.Identifier(role))
    )
    connection.execute(sql.SQL("REVOKE pg_read_all_data FROM {}").format(sql.Identifier(bridge)))
    connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(bridge)))


def _seed_global_setting(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("ALTER ROLE {} SET search_path = attacker, public").format(sql.Identifier(role))
    )


def _reset_global_setting(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(sql.SQL("ALTER ROLE {} RESET search_path").format(sql.Identifier(role)))


def _seed_database_setting(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET work_mem = '64MB'").format(
            sql.Identifier(role), sql.Identifier(database.name)
        )
    )


def _reset_database_setting(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} RESET work_mem").format(
            sql.Identifier(role), sql.Identifier(database.name)
        )
    )


def _owned_relation(database: DatabaseFixture) -> str:
    return f"recovery_owned_{database.name.removeprefix('ctower_test_')[:16]}"


def _seed_owned_object(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    relation = _owned_relation(database)
    connection.execute(sql.SQL("CREATE TABLE {} (value integer)").format(sql.Identifier(relation)))
    connection.execute(
        sql.SQL("ALTER TABLE {} OWNER TO {}").format(sql.Identifier(relation), sql.Identifier(role))
    )


def _drop_owned_object(
    connection: psycopg.Connection[tuple[object, ...]],
    _role: str,
    database: DatabaseFixture,
) -> None:
    connection.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(_owned_relation(database))))


def _seed_object_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(sql.SQL("GRANT DELETE ON tenants TO {}").format(sql.Identifier(role)))


def _revoke_object_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(sql.SQL("REVOKE DELETE ON tenants FROM {}").format(sql.Identifier(role)))


def _seed_database_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
            sql.Identifier(database.name), sql.Identifier(role)
        )
    )


def _revoke_database_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
            sql.Identifier(database.name), sql.Identifier(role)
        )
    )


def _seed_schema_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(sql.Identifier(role)))


def _revoke_schema_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(role))
    )


def _seed_grant_option(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {} WITH GRANT OPTION").format(sql.Identifier(role))
    )


def _revoke_grant_option(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL("REVOKE USAGE ON SCHEMA public FROM {}").format(sql.Identifier(role))
    )


def _seed_default_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE ctower_admin IN SCHEMA public "
            "GRANT DELETE ON TABLES TO {}"
        ).format(sql.Identifier(role))
    )


def _revoke_default_grant(
    connection: psycopg.Connection[tuple[object, ...]],
    role: str,
    _database: DatabaseFixture,
) -> None:
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE ctower_admin IN SCHEMA public "
            "REVOKE DELETE ON TABLES FROM {}"
        ).format(sql.Identifier(role))
    )
