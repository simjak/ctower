"""Exact private table shape and privileges for the migration ledger."""

from __future__ import annotations

import psycopg

from ctower_kernel.record._migration_ledger_models import MigrationStateError

__all__ = [
    "close_ledger_privileges",
    "create_ledger",
    "ledger_exists",
    "ledger_has_server_version",
    "validate_ledger_shape",
    "validate_legacy_ledger_shape",
]

_LEDGER = "ctower_schema_migrations"
_LEDGER_ROLE = "ctower_migration_ledger"


def ledger_exists(connection: psycopg.Connection[tuple[object, ...]]) -> bool:
    row = connection.execute("SELECT to_regclass('public.ctower_schema_migrations')").fetchone()
    return row is not None and row[0] is not None


def create_ledger(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        """
        CREATE TABLE ctower_schema_migrations (
            migration_id text PRIMARY KEY
                CHECK (migration_id ~ '^[0-9]{4}_[a-z0-9_]+[.]sql$'),
            sha256 text NOT NULL
                CHECK (sha256 ~ '^sha256:[0-9a-f]{64}$'),
            application_kind text NOT NULL
                CHECK (application_kind IN ('applied', 'baseline')),
            result_schema_sha256 text NOT NULL
                CHECK (result_schema_sha256 ~ '^sha256:[0-9a-f]{64}$'),
            applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            applied_server_version_num integer
                CHECK (
                    applied_server_version_num IS NULL
                    OR applied_server_version_num > 0
                )
        )
        """
    )
    close_ledger_privileges(connection)
    validate_ledger_shape(connection)


def validate_ledger_shape(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    _validate_ledger_shape_version(connection, versioned=True)


def validate_legacy_ledger_shape(
    connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    _validate_ledger_shape_version(connection, versioned=False)


def _validate_ledger_shape_version(
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    versioned: bool,
) -> None:
    relation = connection.execute(
        """
        SELECT class.relkind, pg_get_userbyid(class.relowner)
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public' AND class.relname = %s
        """,
        (_LEDGER,),
    ).fetchone()
    columns = connection.execute(
        """
        SELECT attribute.attname, format_type(attribute.atttypid, attribute.atttypmod),
               attribute.attnotnull,
               COALESCE(pg_get_expr(default_value.adbin, default_value.adrelid), '')
        FROM pg_attribute AS attribute
        JOIN pg_class AS class ON class.oid = attribute.attrelid
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        LEFT JOIN pg_attrdef AS default_value
          ON default_value.adrelid = attribute.attrelid
         AND default_value.adnum = attribute.attnum
        WHERE namespace.nspname = 'public' AND class.relname = %s
          AND attribute.attnum > 0 AND NOT attribute.attisdropped
        ORDER BY attribute.attnum
        """,
        (_LEDGER,),
    ).fetchall()
    expected = [
        ("migration_id", "text", True, ""),
        ("sha256", "text", True, ""),
        ("application_kind", "text", True, ""),
        ("result_schema_sha256", "text", True, ""),
        ("applied_at", "timestamp with time zone", True, "clock_timestamp()"),
    ]
    if versioned:
        expected.append(("applied_server_version_num", "integer", False, ""))
    if relation != ("r", _LEDGER_ROLE) or columns != expected:
        raise MigrationStateError(
            "ledger-shape-mismatch",
            "ctower_schema_migrations is not the exact owned ledger table",
        )
    constraints = connection.execute(
        """
        SELECT constraint_row.conname, constraint_row.contype,
               pg_get_constraintdef(constraint_row.oid, true)
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS class ON class.oid = constraint_row.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public' AND class.relname = %s
        ORDER BY constraint_row.conname
        """,
        (_LEDGER,),
    ).fetchall()
    expected_constraints = _expected_constraints(versioned=versioned)
    nonowner_access = connection.execute(
        """
        SELECT pg_get_userbyid(entry.grantee), entry.privilege_type, entry.is_grantable
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(
            class.relacl, acldefault('r', class.relowner)
        )) AS entry
        WHERE namespace.nspname = 'public' AND class.relname = %s
          AND entry.grantee <> class.relowner
        ORDER BY 1, 2, 3
        """,
        (_LEDGER,),
    ).fetchall()
    if constraints != expected_constraints or nonowner_access != [
        ("ctower_admin", "SELECT", False)
    ]:
        raise MigrationStateError(
            "ledger-shape-mismatch",
            "ctower_schema_migrations constraints or privileges differ",
        )


def _expected_constraints(*, versioned: bool) -> list[tuple[str, str, str]]:
    constraints = [
        (
            "ctower_schema_migrations_application_kind_check",
            "c",
            "CHECK (application_kind = ANY (ARRAY['applied'::text, 'baseline'::text]))",
        ),
        (
            "ctower_schema_migrations_migration_id_check",
            "c",
            "CHECK (migration_id ~ '^[0-9]{4}_[a-z0-9_]+[.]sql$'::text)",
        ),
        ("ctower_schema_migrations_pkey", "p", "PRIMARY KEY (migration_id)"),
        (
            "ctower_schema_migrations_result_schema_sha256_check",
            "c",
            "CHECK (result_schema_sha256 ~ '^sha256:[0-9a-f]{64}$'::text)",
        ),
        (
            "ctower_schema_migrations_sha256_check",
            "c",
            "CHECK (sha256 ~ '^sha256:[0-9a-f]{64}$'::text)",
        ),
    ]
    if versioned:
        constraints.insert(
            1,
            (
                "ctower_schema_migrations_applied_server_version_num_check",
                "c",
                "CHECK (applied_server_version_num IS NULL OR applied_server_version_num > 0)",
            ),
        )
    return constraints


def ledger_has_server_version(
    connection: psycopg.Connection[tuple[object, ...]],
) -> bool:
    row = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_attribute AS attribute
            JOIN pg_class AS class ON class.oid = attribute.attrelid
            JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = 'public' AND class.relname = %s
              AND attribute.attname = 'applied_server_version_num'
              AND attribute.attnum > 0 AND NOT attribute.attisdropped
        )
        """,
        (_LEDGER,),
    ).fetchone()
    return row is not None and row[0] is True


def close_ledger_privileges(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        """
        REVOKE ALL ON ctower_schema_migrations
        FROM PUBLIC, ctower_admin, ctower_svc, ctower_projection, ctower_runtime,
             ctower_projection_runtime
        """
    )
    connection.execute("GRANT SELECT ON ctower_schema_migrations TO ctower_admin")
