"""Transactional database-migration ledger and fail-closed pre-ledger adoption."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

import psycopg

__all__ = [
    "MigrationAdoptionError",
    "MigrationBaseline",
    "MigrationExecutionError",
    "MigrationScript",
    "MigrationStateError",
    "acquire_migration_control_lock",
    "apply_database_migrations",
    "record_database_migrations",
]

_LEDGER = "ctower_schema_migrations"
_LEDGER_ROLE = "ctower_migration_ledger"
_LEDGER_LOCK = 712040119
_SEMANTIC_CHECKS = "ctower.pre-ledger/v1"
type _SchemaRecord = tuple[str, str, str]
type _SchemaRecords = tuple[_SchemaRecord, ...]


@dataclass(frozen=True, slots=True)
class MigrationScript:
    """One checksum-verified authored database migration."""

    migration_id: str
    sha256: str
    scope: Literal["cluster", "database"]
    content: str


@dataclass(frozen=True, slots=True)
class MigrationBaseline:
    """One exact supported pre-ledger schema state."""

    through: str
    schema_sha256: str
    semantic_checks: Literal["ctower.pre-ledger/v1"]
    # Diagnostic only: canonical schema_sha256 remains the acceptance authority.
    schema_object_sum256: str


@dataclass(frozen=True, slots=True)
class _PendingMigration:
    migration: MigrationScript
    application_kind: Literal["applied", "baseline"]


class MigrationStateError(ValueError):
    """The migration ledger is malformed or contradicts the authored history."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class MigrationAdoptionError(MigrationStateError):
    """A pre-ledger database cannot prove the exact supported baseline."""


class MigrationExecutionError(MigrationStateError):
    """Authored migration SQL failed behind a bounded data-safe error."""


def acquire_migration_control_lock(
    connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    """Serialize the complete cross-connection migration operation."""

    connection.execute("SELECT pg_advisory_lock(%s)", (_LEDGER_LOCK,))


def apply_database_migrations(
    connection: psycopg.Connection[tuple[object, ...]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> tuple[_PendingMigration, ...]:
    """Validate and advance schema; return rows for the narrow ledger authority."""

    ledger_exists = _ledger_exists(connection)
    if ledger_exists:
        _validate_ledger_shape(connection)
        applied = _validated_applied_prefix(connection, migrations, baseline)
        applied_count = len(applied)
    else:
        applied = []
        applied_count = 0
    pending: list[_PendingMigration] = []
    if applied:
        _validate_recorded_application_state(connection, applied, baseline)
    elif _has_preledger_objects(connection):
        baseline_index = _validate_preledger_database(connection, migrations, baseline)
        pending.extend(
            _PendingMigration(migration, "baseline")
            for migration in migrations[: baseline_index + 1]
        )
        applied_count = baseline_index + 1
    for migration in migrations[applied_count:]:
        _execute_migration(connection, migration)
        pending.append(_PendingMigration(migration, "applied"))
    return tuple(pending)


def record_database_migrations(
    connection: psycopg.Connection[tuple[object, ...]],
    pending: tuple[_PendingMigration, ...],
    baseline: MigrationBaseline,
) -> None:
    """Attest and record completed work only as the isolated ledger role."""

    if not pending:
        return
    actual_records = _schema_records(connection)
    actual_fingerprint = _schema_fingerprint(actual_records)
    if pending[-1].migration.migration_id == baseline.through and not hmac.compare_digest(
        actual_fingerprint,
        baseline.schema_sha256,
    ):
        raise MigrationStateError(
            "ledger-attestation-mismatch",
            f"completed schema does not match {baseline.through}",
        )
    if pending[-1].migration.migration_id == baseline.through:
        semantic_rejections = _baseline_semantic_rejections(connection, baseline)
        if semantic_rejections:
            raise MigrationStateError(
                "ledger-semantic-mismatch",
                ", ".join(semantic_rejections),
            )
    connection.execute(f"SET ROLE {_LEDGER_ROLE}")
    if _ledger_exists(connection):
        _validate_ledger_shape(connection)
    else:
        _create_ledger(connection)
    for item in pending:
        _record_migration(
            connection,
            item.migration,
            application_kind=item.application_kind,
            result_schema_sha256=actual_fingerprint,
        )
    _close_ledger_privileges(connection)


def _validate_preledger_database(
    connection: psycopg.Connection[tuple[object, ...]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> int:
    baseline_index = _baseline_index(migrations, baseline)
    actual_records = _schema_records(connection)
    actual_fingerprint = _schema_fingerprint(actual_records)
    if not hmac.compare_digest(actual_fingerprint, baseline.schema_sha256):
        configuration_difference = _persisted_configuration_difference(actual_records)
        if configuration_difference is not None:
            raise MigrationAdoptionError(
                "baseline-configuration-mismatch",
                configuration_difference,
            )
        raise MigrationAdoptionError(
            "baseline-schema-mismatch",
            _schema_difference(
                baseline.schema_sha256,
                actual_fingerprint,
                actual_records,
                expected_object_sum=baseline.schema_object_sum256,
                through=baseline.through,
            ),
        )
    semantic_rejections = _baseline_semantic_rejections(connection, baseline)
    if semantic_rejections:
        raise MigrationAdoptionError(
            "baseline-semantic-mismatch",
            ", ".join(semantic_rejections),
        )
    return baseline_index


def _validate_recorded_application_state(
    connection: psycopg.Connection[tuple[object, ...]],
    applied: list[tuple[str, str, str, str, datetime]],
    baseline: MigrationBaseline,
) -> None:
    actual_fingerprint = _schema_fingerprint(_schema_records(connection))
    if not hmac.compare_digest(actual_fingerprint, applied[-1][3]):
        raise MigrationStateError(
            "ledger-schema-mismatch",
            f"schema does not match the attestation for {applied[-1][0]}",
        )
    if applied[-1][0] == baseline.through and not hmac.compare_digest(
        applied[-1][3],
        baseline.schema_sha256,
    ):
        raise MigrationStateError(
            "ledger-attestation-mismatch",
            f"recorded schema does not match the authored baseline for {baseline.through}",
        )


def _execute_migration(
    connection: psycopg.Connection[tuple[object, ...]],
    migration: MigrationScript,
) -> None:
    try:
        connection.execute(migration.content)
    except psycopg.Error as error:
        raise _migration_execution_error(migration.migration_id, error) from None


def _migration_execution_error(
    migration_id: str,
    error: psycopg.Error,
) -> MigrationExecutionError:
    sqlstate = error.sqlstate or "unknown"
    return MigrationExecutionError(
        "migration-execution-failed",
        (
            f"{migration_id} failed with SQLSTATE {sqlstate}; "
            "inspect access-controlled PostgreSQL diagnostics"
        ),
    )


def _baseline_index(
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> int:
    for index, migration in enumerate(migrations):
        if migration.migration_id == baseline.through:
            return index
    raise MigrationStateError(
        "baseline-manifest-mismatch",
        f"baseline migration is not a database migration: {baseline.through}",
    )


def _ledger_exists(connection: psycopg.Connection[tuple[object, ...]]) -> bool:
    row = connection.execute("SELECT to_regclass('public.ctower_schema_migrations')").fetchone()
    return row is not None and row[0] is not None


def _has_preledger_objects(connection: psycopg.Connection[tuple[object, ...]]) -> bool:
    row = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_class AS class
            JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = 'public'
              AND class.relname <> %s
              AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            UNION ALL
            SELECT 1
            FROM pg_proc AS routine
            JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = 'public'
            UNION ALL
            SELECT 1
            FROM pg_type AS type
            JOIN pg_namespace AS namespace ON namespace.oid = type.typnamespace
            WHERE namespace.nspname = 'public'
              AND type.typtype IN ('d', 'e', 'r')
        )
        """,
        (_LEDGER,),
    ).fetchone()
    return row is not None and row[0] is True


def _create_ledger(connection: psycopg.Connection[tuple[object, ...]]) -> None:
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
            applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    _close_ledger_privileges(connection)
    _validate_ledger_shape(connection)


def _validate_ledger_shape(connection: psycopg.Connection[tuple[object, ...]]) -> None:
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
    if relation != ("r", _LEDGER_ROLE) or columns != expected:
        raise MigrationStateError(
            "ledger-shape-mismatch",
            "ctower_schema_migrations is not the exact owned ledger table",
        )
    constraints = connection.execute(
        """
        SELECT constraint_row.conname, constraint_row.contype,
               pg_get_constraintdef(constraint_row.oid, false)
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS class ON class.oid = constraint_row.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public' AND class.relname = %s
        ORDER BY constraint_row.conname
        """,
        (_LEDGER,),
    ).fetchall()
    expected_constraints = [
        (
            "ctower_schema_migrations_application_kind_check",
            "c",
            "CHECK ((application_kind = ANY (ARRAY['applied'::text, 'baseline'::text])))",
        ),
        (
            "ctower_schema_migrations_migration_id_check",
            "c",
            "CHECK ((migration_id ~ '^[0-9]{4}_[a-z0-9_]+[.]sql$'::text))",
        ),
        ("ctower_schema_migrations_pkey", "p", "PRIMARY KEY (migration_id)"),
        (
            "ctower_schema_migrations_result_schema_sha256_check",
            "c",
            "CHECK ((result_schema_sha256 ~ '^sha256:[0-9a-f]{64}$'::text))",
        ),
        (
            "ctower_schema_migrations_sha256_check",
            "c",
            "CHECK ((sha256 ~ '^sha256:[0-9a-f]{64}$'::text))",
        ),
    ]
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


def _validated_applied_prefix(
    connection: psycopg.Connection[tuple[object, ...]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> list[tuple[str, str, str, str, datetime]]:
    rows = cast(
        list[tuple[str, str, str, str, datetime]],
        connection.execute(
            """
            SELECT migration_id, sha256, application_kind,
                   result_schema_sha256, applied_at
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall(),
    )
    expected_ids = [migration.migration_id for migration in migrations[: len(rows)]]
    actual_ids = [row[0] for row in rows]
    if actual_ids != expected_ids:
        raise MigrationStateError(
            "ledger-history-mismatch",
            "ledger rows are not one contiguous authored migration prefix",
        )
    for row, migration in zip(rows, migrations, strict=False):
        if not hmac.compare_digest(row[1], migration.sha256):
            raise MigrationStateError(
                "ledger-checksum-mismatch",
                f"recorded checksum differs for {migration.migration_id}",
            )
    _validate_baseline_rows(rows, migrations, baseline)
    return rows


def _validate_baseline_rows(
    rows: list[tuple[str, str, str, str, datetime]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> None:
    baseline_index = _baseline_index(migrations, baseline)
    baseline_ids = [row[0] for row in rows if row[2] == "baseline"]
    if baseline_ids and baseline_ids != [
        migration.migration_id for migration in migrations[: baseline_index + 1]
    ]:
        raise MigrationStateError(
            "ledger-baseline-mismatch",
            "baseline rows must be the complete declared pre-ledger history",
        )
    if any(row[2] not in {"applied", "baseline"} for row in rows):
        raise MigrationStateError(
            "ledger-application-kind-mismatch",
            "ledger contains an unknown application kind",
        )


def _record_migration(
    connection: psycopg.Connection[tuple[object, ...]],
    migration: MigrationScript,
    *,
    application_kind: Literal["applied", "baseline"],
    result_schema_sha256: str,
) -> None:
    connection.execute(
        """
        INSERT INTO ctower_schema_migrations (
            migration_id, sha256, application_kind, result_schema_sha256, applied_at
        ) VALUES (%s, %s, %s, %s, clock_timestamp())
        """,
        (
            migration.migration_id,
            migration.sha256,
            application_kind,
            result_schema_sha256,
        ),
    )


def _close_ledger_privileges(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        """
        REVOKE ALL ON ctower_schema_migrations
        FROM PUBLIC, ctower_admin, ctower_svc, ctower_projection, ctower_runtime,
             ctower_projection_runtime
        """
    )
    connection.execute("GRANT SELECT ON ctower_schema_migrations TO ctower_admin")


def _schema_records(
    connection: psycopg.Connection[tuple[object, ...]],
) -> _SchemaRecords:
    records: list[_SchemaRecord] = []
    for query in _SCHEMA_QUERIES:
        parameters = tuple(_LEDGER for _ in range(query.count("%s")))
        records.extend(cast(list[_SchemaRecord], connection.execute(query, parameters).fetchall()))
    return tuple(sorted(records))


def _schema_fingerprint(records: _SchemaRecords) -> str:
    canonical = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _schema_difference(
    expected_fingerprint: str,
    actual_fingerprint: str,
    actual_records: _SchemaRecords,
    *,
    expected_object_sum: str,
    through: str,
) -> str:
    # The additive digest identifies one unexpected dependency-discovered object in
    # linear time. It never authorizes adoption: the canonical SHA-256 comparison did
    # that above and has already failed.
    expected_sum = int(expected_object_sum.removeprefix("sum256:"), 16)
    unexpected_digest = (_schema_object_sum(actual_records) - expected_sum) % (1 << 256)
    for record in actual_records:
        if record[0] == "schema-object" and _record_digest(record) == unexpected_digest:
            kind, identity, _ = record
            return f"unexpected {kind} {identity}"
    return f"expected {expected_fingerprint} through {through}, got {actual_fingerprint}"


def _persisted_configuration_difference(records: _SchemaRecords) -> str | None:
    for kind, identity, _ in records:
        if kind == "persisted-setting":
            return f"unexpected {kind} {identity}"
    return None


def _schema_object_sum(records: _SchemaRecords) -> int:
    return sum(_record_digest(record) for record in records if record[0] == "schema-object") % (
        1 << 256
    )


def _record_digest(record: _SchemaRecord) -> int:
    canonical = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(canonical).digest())


def _baseline_semantic_rejections(
    connection: psycopg.Connection[tuple[object, ...]],
    baseline: MigrationBaseline,
) -> tuple[str, ...]:
    if baseline.semantic_checks != _SEMANTIC_CHECKS:
        raise MigrationStateError(
            "baseline-manifest-mismatch",
            f"unknown semantic checks: {baseline.semantic_checks}",
        )
    rejected = []
    for name, query in _SEMANTIC_QUERIES:
        row = connection.execute(query).fetchone()
        if row is None or row[0] is not False:
            rejected.append(name)
    return tuple(rejected)


# PostgreSQL records schema-contained objects and their internally dependent children
# in pg_depend. Starting at every user schema and following the dependency graph makes
# PostgreSQL itself define the object-kind denominator. The private ledger and all of
# its dependent catalog objects are removed as a dependency-discovered subtree.
_SCHEMA_QUERIES = (
    """
    WITH RECURSIVE user_schemas(classid, objid, objsubid) AS (
        SELECT 'pg_catalog.pg_namespace'::regclass::oid, namespace.oid, 0
        FROM pg_namespace AS namespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND namespace.nspname NOT LIKE 'pg_temp_%%'
          AND namespace.nspname NOT LIKE 'pg_toast_temp_%%'
    ),
    schema_objects(classid, objid, objsubid) AS (
        SELECT * FROM user_schemas
        UNION
        SELECT dependency.classid, dependency.objid, dependency.objsubid
        FROM pg_depend AS dependency
        JOIN schema_objects AS referenced
          ON referenced.classid = dependency.refclassid
         AND referenced.objid = dependency.refobjid
         AND referenced.objsubid = dependency.refobjsubid
        WHERE dependency.deptype <> 'p'
    ),
    ledger_objects(classid, objid, objsubid) AS (
        SELECT 'pg_catalog.pg_class'::regclass::oid, class.oid, 0
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = 'public' AND class.relname = %s
        UNION
        SELECT dependency.classid, dependency.objid, dependency.objsubid
        FROM pg_depend AS dependency
        JOIN ledger_objects AS referenced
          ON referenced.classid = dependency.refclassid
         AND referenced.objid = dependency.refobjid
         AND referenced.objsubid = dependency.refobjsubid
        WHERE dependency.deptype <> 'p'
    )
    SELECT DISTINCT
           'schema-object',
           identified.type || ':' ||
               COALESCE(array_to_string(identified.object_names, '.'), ''),
           jsonb_build_object(
               'names', COALESCE(identified.object_names, ARRAY[]::text[]),
               'arguments', COALESCE(identified.object_args, ARRAY[]::text[])
           )::text
    FROM schema_objects AS object
    CROSS JOIN LATERAL pg_identify_object_as_address(
        object.classid, object.objid, object.objsubid
    ) AS identified
    WHERE NOT EXISTS (
        SELECT 1
        FROM ledger_objects AS ledger
        WHERE ledger.classid = object.classid
          AND ledger.objid = object.objid
          AND ledger.objsubid = object.objsubid
    )
      AND (
          identified.object_names[1] IS NULL
          OR identified.object_names[1] NOT IN ('pg_catalog', 'pg_toast')
      )
    ORDER BY 2, 3
    """,
    # pg_db_role_setting is the complete authored persistence surface behind
    # ALTER DATABASE/ALTER ROLE SET. PostgreSQL does not classify GUCs by whether
    # they alter write semantics, so measure the category instead of maintaining a
    # setting-name list. Current-database rows cover database and database+role
    # settings; role-wide rows cover every ctower-owned authority role.
    """
    WITH persisted_settings AS (
        SELECT setting.setdatabase, setting.setrole, role.rolname,
               unnest(setting.setconfig) AS configured
        FROM pg_db_role_setting AS setting
        LEFT JOIN pg_roles AS role ON role.oid = setting.setrole
        WHERE setting.setdatabase = (
                  SELECT database.oid
                  FROM pg_database AS database
                  WHERE database.datname = current_database()
              )
           OR (
                  setting.setdatabase = 0
              AND role.rolname LIKE 'ctower\\_%%' ESCAPE '\\'
           )
    ),
    normalized AS (
        SELECT CASE
                   WHEN setting.setdatabase <> 0 AND setting.setrole = 0
                       THEN 'database'
                   WHEN setting.setdatabase = 0
                       THEN 'role:' || setting.rolname
                   ELSE 'database-role:' || setting.rolname
               END AS scope,
               split_part(setting.configured, '=', 1) AS name,
               substring(
                   setting.configured FROM strpos(setting.configured, '=') + 1
               ) AS value
        FROM persisted_settings AS setting
    )
    SELECT 'persisted-setting', setting.scope || '.' || setting.name,
           jsonb_build_object('value', setting.value)::text
    FROM normalized AS setting
    ORDER BY setting.scope, setting.name, setting.value
    """,
    """
    SELECT 'relation', class.relname,
           jsonb_build_object(
               'kind', class.relkind,
               'owner', pg_get_userbyid(class.relowner),
               'persistence', class.relpersistence,
               'replica_identity', class.relreplident,
               'row_security', class.relrowsecurity,
               'force_row_security', class.relforcerowsecurity,
               'options', COALESCE((
                   SELECT jsonb_agg(option ORDER BY option)
                   FROM unnest(class.reloptions) AS option
               ), '[]'::jsonb),
               'access_method', COALESCE(access_method.amname, ''),
               'tablespace', COALESCE(tablespace.spcname, ''),
               'inherits', COALESCE((
                   SELECT jsonb_agg(
                       parent_namespace.nspname || '.' || parent.relname
                       ORDER BY inheritance.inhseqno
                   )
                   FROM pg_inherits AS inheritance
                   JOIN pg_class AS parent ON parent.oid = inheritance.inhparent
                   JOIN pg_namespace AS parent_namespace
                     ON parent_namespace.oid = parent.relnamespace
                   WHERE inheritance.inhrelid = class.oid
               ), '[]'::jsonb),
               'partition_key', COALESCE(pg_get_partkeydef(class.oid), ''),
               'partition_bound', COALESCE(pg_get_expr(class.relpartbound, class.oid), ''),
               'foreign_server', COALESCE(foreign_server.srvname, ''),
               'foreign_options', COALESCE((
                   SELECT jsonb_agg(option ORDER BY option)
                   FROM unnest(foreign_table.ftoptions) AS option
               ), '[]'::jsonb),
               'view_definition', CASE
                   WHEN class.relkind IN ('v', 'm') THEN pg_get_viewdef(class.oid, false)
                   ELSE ''
               END
           )::text
    FROM pg_class AS class
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    LEFT JOIN pg_am AS access_method ON access_method.oid = class.relam
    LEFT JOIN pg_tablespace AS tablespace ON tablespace.oid = class.reltablespace
    LEFT JOIN pg_foreign_table AS foreign_table ON foreign_table.ftrelid = class.oid
    LEFT JOIN pg_foreign_server AS foreign_server
      ON foreign_server.oid = foreign_table.ftserver
    WHERE namespace.nspname = 'public' AND class.relname <> %s
      AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    ORDER BY class.relname
    """,
    """
    SELECT 'policy', class.relname || '.' || policy.polname,
           jsonb_build_object(
               'permissive', policy.polpermissive,
               'command', policy.polcmd,
               'roles', COALESCE((
                   SELECT jsonb_agg(
                       CASE WHEN role_id = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(role_id) END
                       ORDER BY CASE WHEN role_id = 0 THEN 'PUBLIC'
                                     ELSE pg_get_userbyid(role_id) END
                   )
                   FROM unnest(policy.polroles) AS role_id
               ), '[]'::jsonb),
               'using', COALESCE(pg_get_expr(policy.polqual, policy.polrelid), ''),
               'check', COALESCE(pg_get_expr(policy.polwithcheck, policy.polrelid), '')
           )::text
    FROM pg_policy AS policy
    JOIN pg_class AS class ON class.oid = policy.polrelid
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    WHERE namespace.nspname = 'public' AND class.relname <> %s
    ORDER BY class.relname, policy.polname
    """,
    """
    SELECT 'column', class.relname || '.' || attribute.attnum || '.' || attribute.attname,
           jsonb_build_object(
               'type', format_type(attribute.atttypid, attribute.atttypmod),
               'not_null', attribute.attnotnull,
               'identity', attribute.attidentity,
               'generated', attribute.attgenerated,
               'default', COALESCE(pg_get_expr(default_value.adbin, default_value.adrelid), ''),
               'collation', CASE WHEN attribute.attcollation = 0 THEN ''
                   ELSE attribute.attcollation::regcollation::text END,
               'storage', attribute.attstorage,
               'compression', attribute.attcompression
           )::text
    FROM pg_attribute AS attribute
    JOIN pg_class AS class ON class.oid = attribute.attrelid
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    LEFT JOIN pg_attrdef AS default_value
      ON default_value.adrelid = attribute.attrelid
     AND default_value.adnum = attribute.attnum
    WHERE namespace.nspname = 'public' AND class.relname <> %s
      AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
      AND attribute.attnum > 0 AND NOT attribute.attisdropped
    ORDER BY class.relname, attribute.attnum
    """,
    """
    SELECT 'constraint',
           COALESCE(class.relname, type.typname) || '.' || constraint_row.conname,
           jsonb_build_object(
               'type', constraint_row.contype,
               'deferrable', constraint_row.condeferrable,
               'deferred', constraint_row.condeferred,
               'validated', constraint_row.convalidated,
               'no_inherit', constraint_row.connoinherit,
               'definition', pg_get_constraintdef(constraint_row.oid, false)
           )::text
    FROM pg_constraint AS constraint_row
    JOIN pg_namespace AS namespace ON namespace.oid = constraint_row.connamespace
    LEFT JOIN pg_class AS class ON class.oid = constraint_row.conrelid
    LEFT JOIN pg_type AS type ON type.oid = constraint_row.contypid
    WHERE namespace.nspname = 'public'
      AND COALESCE(class.relname, '') <> %s
    ORDER BY COALESCE(class.relname, type.typname), constraint_row.conname
    """,
    """
    SELECT 'index', table_class.relname || '.' || index_class.relname,
           jsonb_build_object(
               'definition', pg_get_indexdef(index.indexrelid, 0, false),
               'unique', index.indisunique,
               'primary', index.indisprimary,
               'exclusion', index.indisexclusion,
               'immediate', index.indimmediate,
               'clustered', index.indisclustered,
               'valid', index.indisvalid,
               'ready', index.indisready,
               'replica_identity', index.indisreplident
           )::text
    FROM pg_index AS index
    JOIN pg_class AS table_class ON table_class.oid = index.indrelid
    JOIN pg_class AS index_class ON index_class.oid = index.indexrelid
    JOIN pg_namespace AS namespace ON namespace.oid = table_class.relnamespace
    WHERE namespace.nspname = 'public' AND table_class.relname <> %s
    ORDER BY table_class.relname, index_class.relname
    """,
    """
    SELECT 'routine',
           routine.proname || '(' || pg_get_function_identity_arguments(routine.oid) || ')',
           jsonb_build_object(
               'definition', pg_get_functiondef(routine.oid),
               'owner', pg_get_userbyid(routine.proowner),
               'kind', routine.prokind,
               'language', language.lanname,
               'volatility', routine.provolatile,
               'parallel', routine.proparallel,
               'strict', routine.proisstrict,
               'leakproof', routine.proleakproof,
               'security_definer', routine.prosecdef,
               'configuration', COALESCE(routine.proconfig, ARRAY[]::text[])
           )::text
    FROM pg_proc AS routine
    JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
    JOIN pg_language AS language ON language.oid = routine.prolang
    WHERE namespace.nspname = 'public' AND routine.proname <> %s
    ORDER BY routine.proname, pg_get_function_identity_arguments(routine.oid)
    """,
    """
    SELECT 'trigger', class.relname || '.' || trigger.tgname,
           jsonb_build_object(
               'definition', pg_get_triggerdef(trigger.oid, false),
               'enabled', trigger.tgenabled
           )::text
    FROM pg_trigger AS trigger
    JOIN pg_class AS class ON class.oid = trigger.tgrelid
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    WHERE namespace.nspname = 'public' AND class.relname <> %s
      AND NOT trigger.tgisinternal
    ORDER BY class.relname, trigger.tgname
    """,
    """
    SELECT 'constraint-trigger',
           identified.type || ':' ||
               COALESCE(array_to_string(identified.object_names, '.'), '') || ':' ||
               class_namespace.nspname || '.' || class.relname || ':' ||
               routine_namespace.nspname || '.' || routine.proname || '(' ||
               pg_get_function_identity_arguments(routine.oid) || '):' ||
               trigger.tgtype::text,
           jsonb_build_object(
               'constraint_names', COALESCE(
                   identified.object_names, ARRAY[]::text[]
               ),
               'constraint_arguments', COALESCE(
                   identified.object_args, ARRAY[]::text[]
               ),
               'relation', class_namespace.nspname || '.' || class.relname,
               'function', routine_namespace.nspname || '.' || routine.proname || '(' ||
                   pg_get_function_identity_arguments(routine.oid) || ')',
               'type', trigger.tgtype,
               'enabled', trigger.tgenabled,
               'deferrable', trigger.tgdeferrable,
               'initially_deferred', trigger.tginitdeferred
           )::text
    FROM pg_trigger AS trigger
    JOIN pg_constraint AS constraint_row
      ON constraint_row.oid = trigger.tgconstraint
    JOIN pg_namespace AS constraint_namespace
      ON constraint_namespace.oid = constraint_row.connamespace
    JOIN pg_class AS class ON class.oid = trigger.tgrelid
    JOIN pg_namespace AS class_namespace ON class_namespace.oid = class.relnamespace
    JOIN pg_proc AS routine ON routine.oid = trigger.tgfoid
    JOIN pg_namespace AS routine_namespace
      ON routine_namespace.oid = routine.pronamespace
    CROSS JOIN LATERAL pg_identify_object_as_address(
        'pg_catalog.pg_constraint'::regclass::oid, constraint_row.oid, 0
    ) AS identified
    WHERE constraint_namespace.nspname = 'public'
      AND class.relname <> %s
      AND trigger.tgisinternal
      AND trigger.tgconstraint <> 0
    ORDER BY 2, 3
    """,
    """
    SELECT 'sequence', class.relname,
           jsonb_build_object(
               'type', format_type(sequence.seqtypid, NULL),
               'start', sequence.seqstart,
               'increment', sequence.seqincrement,
               'maximum', sequence.seqmax,
               'minimum', sequence.seqmin,
               'cache', sequence.seqcache,
               'cycle', sequence.seqcycle
           )::text
    FROM pg_sequence AS sequence
    JOIN pg_class AS class ON class.oid = sequence.seqrelid
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    WHERE namespace.nspname = 'public' AND class.relname <> %s
    ORDER BY class.relname
    """,
    """
    SELECT 'type', type.typname,
           jsonb_build_object(
               'kind', type.typtype,
               'base', CASE WHEN type.typbasetype = 0 THEN ''
                   ELSE format_type(type.typbasetype, type.typtypmod) END,
               'not_null', type.typnotnull,
               'default', COALESCE(type.typdefault, ''),
               'collation', CASE WHEN type.typcollation = 0 THEN ''
                   ELSE type.typcollation::regcollation::text END,
               'enum', COALESCE((
                   SELECT jsonb_agg(enum.enumlabel ORDER BY enum.enumsortorder)
                   FROM pg_enum AS enum WHERE enum.enumtypid = type.oid
               ), '[]'::jsonb),
               'composite_attributes', COALESCE((
                   SELECT jsonb_agg(
                       jsonb_build_object(
                           'number', attribute.attnum,
                           'name', attribute.attname,
                           'type', format_type(attribute.atttypid, attribute.atttypmod),
                           'not_null', attribute.attnotnull,
                           'collation', CASE WHEN attribute.attcollation = 0 THEN ''
                               ELSE attribute.attcollation::regcollation::text END
                       )
                       ORDER BY attribute.attnum
                   )
                   FROM pg_attribute AS attribute
                   WHERE attribute.attrelid = type.typrelid
                     AND attribute.attnum > 0 AND NOT attribute.attisdropped
               ), '[]'::jsonb),
               'range', COALESCE((
                   SELECT jsonb_build_object(
                       'range_type', format_type(range_row.rngtypid, NULL),
                       'multirange_type', format_type(range_row.rngmultitypid, NULL),
                       'subtype', format_type(range_row.rngsubtype, NULL),
                       'collation', CASE WHEN range_row.rngcollation = 0 THEN ''
                           ELSE range_row.rngcollation::regcollation::text END,
                       'operator_class',
                           operator_namespace.nspname || '.' || operator_class.opcname,
                       'canonical', CASE WHEN range_row.rngcanonical = 0 THEN ''
                           ELSE range_row.rngcanonical::regprocedure::text END,
                       'subtype_diff', CASE WHEN range_row.rngsubdiff = 0 THEN ''
                           ELSE range_row.rngsubdiff::regprocedure::text END
                   )
                   FROM pg_range AS range_row
                   JOIN pg_opclass AS operator_class
                     ON operator_class.oid = range_row.rngsubopc
                   JOIN pg_namespace AS operator_namespace
                     ON operator_namespace.oid = operator_class.opcnamespace
                   WHERE type.oid IN (range_row.rngtypid, range_row.rngmultitypid)
               ), '{}'::jsonb)
           )::text
    FROM pg_type AS type
    JOIN pg_namespace AS namespace ON namespace.oid = type.typnamespace
    WHERE namespace.nspname = 'public' AND type.typname <> %s
      AND type.typtype IN ('c', 'd', 'e', 'm', 'r')
    ORDER BY type.typname
    """,
    """
    SELECT 'extended-statistics', statistics.stxname,
           jsonb_build_object(
               'owner', pg_get_userbyid(statistics.stxowner),
               'kinds', statistics.stxkind,
               'keys', statistics.stxkeys::text,
               'expressions', COALESCE(pg_get_expr(
                   statistics.stxexprs, statistics.stxrelid
               ), ''),
               'definition', pg_get_statisticsobjdef(statistics.oid)
           )::text
    FROM pg_statistic_ext AS statistics
    JOIN pg_namespace AS namespace ON namespace.oid = statistics.stxnamespace
    WHERE namespace.nspname = 'public'
    ORDER BY statistics.stxname
    """,
    """
    SELECT 'comment',
           identified.type || ':' ||
               COALESCE(array_to_string(identified.object_names, '.'), ''),
           description.description
    FROM pg_description AS description
    CROSS JOIN LATERAL pg_identify_object_as_address(
        description.classoid, description.objoid, description.objsubid
    ) AS identified
    WHERE identified.object_names[1] = 'public'
      AND NOT (%s = ANY(identified.object_names))
    ORDER BY 2, 3
    """,
    """
    SELECT 'security-label',
           identified.type || ':' ||
               COALESCE(array_to_string(identified.object_names, '.'), '') || '.' ||
               security_label.provider,
           security_label.label
    FROM pg_seclabel AS security_label
    CROSS JOIN LATERAL pg_identify_object_as_address(
        security_label.classoid, security_label.objoid, security_label.objsubid
    ) AS identified
    WHERE identified.object_names[1] = 'public'
      AND NOT (%s = ANY(identified.object_names))
    ORDER BY 2, 3
    """,
    """
    SELECT 'publication', publication.pubname,
           jsonb_build_object(
               'owner', pg_get_userbyid(publication.pubowner),
               'all_tables', publication.puballtables,
               'insert', publication.pubinsert,
               'update', publication.pubupdate,
               'delete', publication.pubdelete,
               'truncate', publication.pubtruncate,
               'via_partition_root', publication.pubviaroot,
               'tables', COALESCE((
                   SELECT jsonb_agg(
                       jsonb_build_object(
                           'name', member_namespace.nspname || '.' || member.relname,
                           'filter', COALESCE(
                               pg_get_expr(membership.prqual, membership.prrelid), ''
                           ),
                           'columns', COALESCE((
                               SELECT jsonb_agg(attribute.attname ORDER BY attribute.attnum)
                               FROM unnest(membership.prattrs) AS number
                               JOIN pg_attribute AS attribute
                                 ON attribute.attrelid = membership.prrelid
                                AND attribute.attnum = number
                           ), '[]'::jsonb)
                       )
                       ORDER BY member_namespace.nspname, member.relname
                   )
                   FROM pg_publication_rel AS membership
                   JOIN pg_class AS member ON member.oid = membership.prrelid
                   JOIN pg_namespace AS member_namespace
                     ON member_namespace.oid = member.relnamespace
                   WHERE membership.prpubid = publication.oid
               ), '[]'::jsonb),
               'schemas', COALESCE((
                   SELECT jsonb_agg(namespace.nspname ORDER BY namespace.nspname)
                   FROM pg_publication_namespace AS membership
                   JOIN pg_namespace AS namespace
                     ON namespace.oid = membership.pnnspid
                   WHERE membership.pnpubid = publication.oid
               ), '[]'::jsonb)
           )::text
    FROM pg_publication AS publication
    ORDER BY publication.pubname
    """,
    """
    WITH access AS (
        SELECT 'schema'::text AS kind, namespace.nspname::text AS identity,
               entry.grantor, entry.grantee, entry.privilege_type, entry.is_grantable
        FROM pg_namespace AS namespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(namespace.nspacl, acldefault('n', namespace.nspowner))
        ) AS entry
        WHERE namespace.nspname = 'public'
        UNION ALL
        SELECT 'relation', class.relname, entry.grantor, entry.grantee,
               entry.privilege_type, entry.is_grantable
        FROM pg_class AS class
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(
            class.relacl,
            acldefault(CASE WHEN class.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END,
                       class.relowner)
        )) AS entry
        WHERE namespace.nspname = 'public' AND class.relname <> %s
          AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
        UNION ALL
        SELECT 'column', class.relname || '.' || attribute.attname,
               entry.grantor, entry.grantee, entry.privilege_type, entry.is_grantable
        FROM pg_attribute AS attribute
        JOIN pg_class AS class ON class.oid = attribute.attrelid
        JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
        CROSS JOIN LATERAL aclexplode(attribute.attacl) AS entry
        WHERE namespace.nspname = 'public' AND class.relname <> %s
          AND attribute.attacl IS NOT NULL
        UNION ALL
        SELECT 'routine',
               routine.proname || '(' || pg_get_function_identity_arguments(routine.oid) || ')',
               entry.grantor, entry.grantee, entry.privilege_type, entry.is_grantable
        FROM pg_proc AS routine
        JOIN pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(routine.proacl, acldefault('f', routine.proowner))
        ) AS entry
        WHERE namespace.nspname = 'public'
    )
    SELECT 'acl', access.kind || '.' || access.identity || '.' ||
           CASE WHEN access.grantee = 0 THEN 'PUBLIC'
                ELSE pg_get_userbyid(access.grantee) END || '.' ||
           access.privilege_type,
           jsonb_build_object(
               'grantor', pg_get_userbyid(access.grantor),
               'grantable', access.is_grantable
           )::text
    FROM access
    ORDER BY access.kind, access.identity,
             CASE WHEN access.grantee = 0 THEN 'PUBLIC'
                  ELSE pg_get_userbyid(access.grantee) END,
             access.privilege_type, pg_get_userbyid(access.grantor)
    """,
    """
    SELECT 'default_acl',
           pg_get_userbyid(default_acl.defaclrole) || '.' ||
           COALESCE(namespace.nspname, '') || '.' ||
           default_acl.defaclobjtype::text || '.' ||
           CASE WHEN entry.grantee = 0 THEN 'PUBLIC'
                ELSE pg_get_userbyid(entry.grantee) END || '.' || entry.privilege_type,
           jsonb_build_object(
               'grantor', pg_get_userbyid(entry.grantor),
               'grantable', entry.is_grantable
           )::text
    FROM pg_default_acl AS default_acl
    LEFT JOIN pg_namespace AS namespace ON namespace.oid = default_acl.defaclnamespace
    CROSS JOIN LATERAL aclexplode(default_acl.defaclacl) AS entry
    WHERE (namespace.nspname = 'public' OR default_acl.defaclnamespace = 0)
    ORDER BY pg_get_userbyid(default_acl.defaclrole), namespace.nspname,
             default_acl.defaclobjtype::text,
             CASE WHEN entry.grantee = 0 THEN 'PUBLIC'
                  ELSE pg_get_userbyid(entry.grantee) END,
             entry.privilege_type, pg_get_userbyid(entry.grantor)
    """,
)


_SEMANTIC_QUERIES = (
    (
        "record-position-ledger",
        """
        SELECT
            (SELECT count(*) FROM record_position_ledger) <> 1
            OR (SELECT last_position FROM record_position_ledger WHERE singleton)
               IS DISTINCT FROM (SELECT COALESCE(max(record_position), 0) FROM events)
        """,
    ),
    (
        "record-position-history-unprovable",
        """
        SELECT EXISTS (SELECT 1 FROM events)
        """,
    ),
    (
        "durability-policy-singleton",
        "SELECT (SELECT count(*) FROM durability_policy_state) <> 1",
    ),
    (
        "proof-verdict-sequence-backfill",
        """
        SELECT EXISTS (
            SELECT 1
            FROM proof_verdicts AS verdict
            LEFT JOIN events AS event
              ON event.tenant_id = verdict.tenant_id
             AND event.aggregate_id = verdict.proof_id
             AND event.actor_principal_id = verdict.reviewer_id
             AND event.client_command_id = verdict.client_command_id
             AND event.kind = 'proof.changed'
             AND event.sequence = verdict.proof_sequence
            WHERE event.event_id IS NULL
        )
        """,
    ),
    (
        "event-link-backfill",
        """
        WITH expected AS (
            SELECT event_id, tenant_id,
                   CASE WHEN kind = 'work.changed' THEN 'work' ELSE 'ticket' END AS subject_kind,
                   aggregate_id AS subject_id
            FROM events
            WHERE kind IN ('ticket.created', 'ticket.custody_transferred', 'work.changed')
            UNION
            SELECT event.event_id, event.tenant_id, 'workflow', run.workflow_run_id
            FROM events AS event
            JOIN workflow_runs AS run
              ON run.tenant_id = event.tenant_id
             AND run.workflow_run_id = event.aggregate_id
            WHERE event.kind = 'workflow.changed'
            UNION
            SELECT event.event_id, event.tenant_id, 'ticket', run.ticket_id
            FROM events AS event
            JOIN workflow_runs AS run
              ON run.tenant_id = event.tenant_id
             AND run.workflow_run_id = event.aggregate_id
            WHERE event.kind = 'workflow.changed'
            UNION
            SELECT event.event_id, event.tenant_id, 'proof', bundle.proof_id
            FROM events AS event
            JOIN proof_bundles AS bundle
              ON bundle.tenant_id = event.tenant_id
             AND bundle.proof_id = event.aggregate_id
            WHERE event.kind = 'proof.changed'
            UNION
            SELECT event.event_id, event.tenant_id, 'ticket', bundle.ticket_id
            FROM events AS event
            JOIN proof_bundles AS bundle
              ON bundle.tenant_id = event.tenant_id
             AND bundle.proof_id = event.aggregate_id
            WHERE event.kind = 'proof.changed'
        )
        SELECT EXISTS (
            (SELECT * FROM expected
             EXCEPT
             SELECT event_id, tenant_id, subject_kind, subject_id FROM event_links)
            UNION ALL
            (SELECT event_id, tenant_id, subject_kind, subject_id FROM event_links
             EXCEPT
             SELECT * FROM expected)
        )
        """,
    ),
    (
        "durability-subject-head-backfill",
        """
        WITH expected AS (
            SELECT DISTINCT ON (link.tenant_id, link.subject_kind, link.subject_id)
                   link.tenant_id, link.subject_kind, link.subject_id,
                   event.actor_principal_id AS principal_id,
                   event.client_command_id, event.server_time AS updated_at
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            JOIN command_results AS result
              ON result.tenant_id = event.tenant_id
             AND result.principal_id = event.actor_principal_id
             AND result.client_command_id = event.client_command_id
            ORDER BY link.tenant_id, link.subject_kind, link.subject_id,
                     event.record_position DESC, event.event_id DESC
        )
        SELECT EXISTS (
            (SELECT * FROM expected
             EXCEPT
             SELECT tenant_id, subject_kind, subject_id, principal_id,
                    client_command_id, updated_at
             FROM durability_subject_heads)
            UNION ALL
            (SELECT tenant_id, subject_kind, subject_id, principal_id,
                    client_command_id, updated_at
             FROM durability_subject_heads
             EXCEPT
             SELECT * FROM expected)
        )
        """,
    ),
    (
        "workflow-start-fact-backfill",
        """
        WITH expected AS (
            SELECT event.event_id, event.tenant_id, run.workflow_run_id, run.ticket_id,
                   run.activity_class, event.server_time AS recorded_at
            FROM events AS event
            JOIN workflow_runs AS run
              ON run.tenant_id = event.tenant_id
             AND run.workflow_run_id = event.aggregate_id
            WHERE event.kind = 'workflow.changed'
              AND event.payload ->> 'operation' = 'start'
        )
        SELECT EXISTS (
            (SELECT * FROM expected
             EXCEPT
             SELECT event_id, tenant_id, workflow_run_id, ticket_id,
                    activity_class, recorded_at
             FROM workflow_start_facts)
            UNION ALL
            (SELECT event_id, tenant_id, workflow_run_id, ticket_id,
                    activity_class, recorded_at
             FROM workflow_start_facts
             EXCEPT
             SELECT * FROM expected)
        )
        """,
    ),
)
