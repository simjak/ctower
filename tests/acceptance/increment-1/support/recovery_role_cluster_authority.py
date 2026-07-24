"""Bounded sibling-database authority cases for reusable recovery roles."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

import psycopg
from psycopg import sql
from support.postgres import create_database, drop_database, start_postgres, stop_postgres

from ctower_kernel.record.postgres import (
    RecoveryRoleConfigurationError,
    provision_database_roles,
)

__all__ = ["assert_sibling_database_authority_is_rejected"]

ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "packages/ctower-kernel/migrations/0020_recovery_roles.sql"
ROLE = "ctower_restore"
_SANITIZED_ERROR = "recovery role configuration does not match the declared catalog shape"


def assert_sibling_database_authority_is_rejected(
    authority_kind: Literal["ownership", "acl"],
) -> None:
    """Reject one cluster-global authority path without changing its fingerprint."""

    server = start_postgres()
    database = create_database(server)
    sibling = create_database(server)
    relation = f"recovery_sibling_{uuid4().hex[:16]}"
    try:
        provision_database_roles(database.admin_dsn)
        _seed_authority(sibling.admin_dsn, relation, authority_kind)
        before = _authority_fingerprint(database.admin_dsn, sibling.admin_dsn, relation)

        assert _has_authority(sibling.admin_dsn, relation, authority_kind) is True
        migration_outcomes = _migration_outcomes(database.admin_dsn)
        provisioning_outcomes = _provisioning_outcomes(database.admin_dsn)

        assert _authority_fingerprint(database.admin_dsn, sibling.admin_dsn, relation) == before
        assert _has_authority(sibling.admin_dsn, relation, authority_kind) is True
        evidence = (
            f"{authority_kind}: migration={migration_outcomes}, "
            f"provisioning={provisioning_outcomes}, retained_authority=True"
        )
        assert migration_outcomes == (_SANITIZED_ERROR, _SANITIZED_ERROR), evidence
        assert provisioning_outcomes == (_SANITIZED_ERROR, _SANITIZED_ERROR), evidence
    finally:
        drop_database(sibling)
        drop_database(database)
        stop_postgres(server)


def _seed_authority(
    sibling_dsn: str,
    relation: str,
    authority_kind: Literal["ownership", "acl"],
) -> None:
    with psycopg.connect(sibling_dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE TABLE {} (value integer)").format(sql.Identifier(relation))
        )
        if authority_kind == "ownership":
            connection.execute(
                sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                    sql.Identifier(relation), sql.Identifier(ROLE)
                )
            )
        else:
            connection.execute(
                sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.Identifier(relation), sql.Identifier(ROLE)
                )
            )


def _has_authority(
    sibling_dsn: str,
    relation: str,
    authority_kind: Literal["ownership", "acl"],
) -> bool:
    privilege = "INSERT" if authority_kind == "ownership" else "SELECT"
    with psycopg.connect(sibling_dsn) as connection:
        row = connection.execute(
            "SELECT has_table_privilege(%s, %s, %s)",
            (ROLE, f"public.{relation}", privilege),
        ).fetchone()
    assert row is not None
    return bool(row[0])


def _migration_outcomes(admin_dsn: str) -> tuple[str, ...]:
    outcomes: list[str] = []
    script = MIGRATION.read_text(encoding="utf-8")
    for _ in range(2):
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            try:
                connection.execute(script)
            except psycopg.errors.RaiseException as error:
                outcomes.append(str(error.diag.message_primary))
            else:
                outcomes.append("accepted")
    return tuple(outcomes)


def _provisioning_outcomes(admin_dsn: str) -> tuple[str, ...]:
    outcomes: list[str] = []
    for _ in range(2):
        try:
            provision_database_roles(admin_dsn)
        except RecoveryRoleConfigurationError as error:
            outcomes.append(str(error))
        else:
            outcomes.append("accepted")
    return tuple(outcomes)


def _authority_fingerprint(
    admin_dsn: str,
    sibling_dsn: str,
    relation: str,
) -> tuple[tuple[tuple[object, ...], ...], ...]:
    with psycopg.connect(admin_dsn) as connection:
        roles = tuple(
            connection.execute(
                """
                SELECT oid, rolname, rolcanlogin, rolinherit, rolcreaterole,
                    rolcreatedb, rolreplication, rolbypassrls, rolsuper
                FROM pg_roles
                WHERE rolname LIKE 'ctower\\_%' ESCAPE '\\'
                ORDER BY rolname
                """
            ).fetchall()
        )
        dependencies = tuple(
            connection.execute(
                """
                SELECT dbid, classid, objid, objsubid, refobjid, deptype
                FROM pg_shdepend
                WHERE refclassid = 'pg_authid'::regclass
                  AND refobjid = (SELECT oid FROM pg_roles WHERE rolname = %s)
                ORDER BY dbid, classid, objid, objsubid, refobjid, deptype
                """,
                (ROLE,),
            ).fetchall()
        )
    with psycopg.connect(sibling_dsn) as connection:
        sibling_relation = tuple(
            connection.execute(
                """
                SELECT pg_get_userbyid(relation.relowner),
                    COALESCE(array_to_string(relation.relacl, ','), '')
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public' AND relation.relname = %s
                """,
                (relation,),
            ).fetchall()
        )
    return roles, dependencies, sibling_relation
