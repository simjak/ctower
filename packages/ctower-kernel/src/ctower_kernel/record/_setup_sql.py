"""Checksum-locked migration and local bootstrap provisioning."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal, TextIO
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ctower_kernel.record import _migration_control_sql
from ctower_kernel.record._durability_probe_role_sql import (
    DURABILITY_PROBE_ROLE,
    close_durability_probe_boundary,
    probe_role_rejection_reasons,
    quarantine_durability_probe,
)
from ctower_kernel.record._migration_ledger_sql import (
    MigrationAdoptionError,
    MigrationAdvanceTransition,
    MigrationBaseline,
    MigrationExecutionError,
    MigrationPreconditionError,
    MigrationScript,
    MigrationStateError,
    _migration_execution_error,
    apply_database_migrations,
    record_database_migrations,
    upgrade_migration_ledger,
)
from ctower_kernel.record._recovery_role_shape_sql import (
    RecoveryRoleConfigurationError,
    validate_recovery_role_shapes,
)
from ctower_kernel.record.identifiers import uuid7 as _uuid7

__all__ = [
    "MigrationAdoptionError",
    "MigrationExecutionError",
    "MigrationPreconditionError",
    "MigrationStateError",
    "RecoveryRoleConfigurationError",
    "apply_migrations",
    "configure_development_durability",
    "provision_bootstrap",
    "provision_database_roles",
    "provision_principal_credential",
]

MINIMUM_CAPABILITY_LENGTH = 32
MAXIMUM_CAPABILITY_LENGTH = 256
PROJECTION_RUNTIME_ROLE = "ctower_projection_runtime"
# Projection workers should exit promptly on SIGTERM; five seconds tolerates backend cleanup
# without allowing role provisioning to wait without a bound.
PROJECTION_SESSION_TERMINATION_TIMEOUT_MS = 5_000
_SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


class _PreMigrationBackupRecovery(BaseModel):
    """The only safe uses of a backup predating durability authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    isolated_recovery: Literal[True]
    live_restore_before_later_acceptance_or_reactivation: Literal[True]


class _PostCutoverRecovery(BaseModel):
    """The recovery obligation once durable acceptance may have occurred."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    requires_durability_aware_build_or_forward_compensation: Literal[True]
    preserve_immutable_facts: tuple[
        Literal["commands"],
        Literal["events"],
        Literal["acknowledgements"],
        Literal["finalizations"],
    ]


class _RecoveryContract(BaseModel):
    """Machine-validated recovery phases for the durability migration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pre_migration_backup: _PreMigrationBackupRecovery
    after_cutover_or_later_acceptance: _PostCutoverRecovery


class _MigrationDeclaration(BaseModel):
    """One strict upgrade and rollback declaration from the authored manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    sha256: str
    scope: Literal["cluster", "database"] = "database"
    minimum_service_version: str
    maximum_service_version: str
    forward_test: str
    rollback_or_forward_compensation: str
    backup_checkpoint: str
    recovery_contract: _RecoveryContract | None = None

    @field_validator("path")
    @classmethod
    def _valid_path(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}_[a-z0-9_]+\.sql", value):
            raise ValueError("migration path must be one numbered SQL filename")
        return value

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("migration checksum must be one lowercase SHA-256 digest")
        return value

    @field_validator("minimum_service_version", "maximum_service_version")
    @classmethod
    def _valid_version(cls, value: str) -> str:
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("migration compatibility must be one exact service version")
        return value

    @field_validator("forward_test")
    @classmethod
    def _valid_forward_test(cls, value: str) -> str:
        pattern = r"pytest:tests/[A-Za-z0-9_./-]+\.py::test_[a-z0-9_]+"
        if re.fullmatch(pattern, value) is None:
            raise ValueError("migration forward test must be one exact pytest node")
        return value

    @field_validator("rollback_or_forward_compensation", "backup_checkpoint")
    @classmethod
    def _nonempty_procedure(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration recovery declarations cannot be empty")
        return value

    @model_validator(mode="after")
    def _ordered_compatibility(self) -> _MigrationDeclaration:
        minimum = tuple(map(int, self.minimum_service_version.split(".")))
        maximum = tuple(map(int, self.maximum_service_version.split(".")))
        if minimum > maximum:
            raise ValueError("minimum compatible service version exceeds maximum")
        if self.path == "0013_durability_authority.sql" and self.recovery_contract is None:
            raise ValueError("durability authority requires a semantic recovery contract")
        return self


class _AdoptionBaseline(BaseModel):
    """One exact current pre-ledger state eligible for adoption."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    through: str
    schema_sha256: str
    semantic_checks: Literal["ctower.pre-ledger/v1"]
    schema_object_sum256: str

    @field_validator("through")
    @classmethod
    def _valid_through(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}_[a-z0-9_]+\.sql", value):
            raise ValueError("adoption baseline must name one numbered SQL filename")
        return value

    @field_validator("schema_sha256")
    @classmethod
    def _valid_schema_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("adoption baseline must have one lowercase SHA-256 digest")
        return value

    @field_validator("schema_object_sum256")
    @classmethod
    def _valid_schema_object_sum256(cls, value: str) -> str:
        if not re.fullmatch(r"sum256:[0-9a-f]{64}", value):
            raise ValueError("adoption baseline must have one lowercase object-sum digest")
        return value


class _LedgerAdvanceTransition(BaseModel):
    """One exact cluster-created schema state eligible to advance a ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recorded_through: str
    recorded_schema_sha256: str
    cluster_through: str
    cluster_sha256: str
    postgres_major: Literal[17]
    result_schema_sha256: str
    schema_object_sum256: str
    pending_database_from: str
    pending_database_through: str

    @field_validator(
        "recorded_through",
        "cluster_through",
        "pending_database_from",
        "pending_database_through",
    )
    @classmethod
    def _valid_migration_path(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}_[a-z0-9_]+\.sql", value):
            raise ValueError("ledger advance transition must name numbered SQL filenames")
        return value

    @field_validator("recorded_schema_sha256", "cluster_sha256", "result_schema_sha256")
    @classmethod
    def _valid_transition_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("ledger advance transition must have lowercase SHA-256 digests")
        return value

    @field_validator("schema_object_sum256")
    @classmethod
    def _valid_transition_object_sum256(cls, value: str) -> str:
        if not re.fullmatch(r"sum256:[0-9a-f]{64}", value):
            raise ValueError("ledger advance transition must have one lowercase object sum")
        return value


class _MigrationManifest(BaseModel):
    """The one strict ordered migration declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_id: Literal["ctower.migrations/v4"] = Field(alias="schema")
    adoption_baseline: _AdoptionBaseline
    ledger_advance_transitions: tuple[_LedgerAdvanceTransition, ...]
    migrations: tuple[_MigrationDeclaration, ...]

    @model_validator(mode="after")
    def _ordered_unique_paths(self) -> _MigrationManifest:
        paths = tuple(entry.path for entry in self.migrations)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("migration paths must be unique and ordered")
        database_paths = tuple(entry.path for entry in self.migrations if entry.scope == "database")
        if not database_paths or self.adoption_baseline.through != database_paths[-1]:
            raise ValueError("adoption baseline must name the final database migration")
        _validate_transition_declarations(
            self.migrations,
            database_paths,
            self.ledger_advance_transitions,
        )
        return self


def _validate_transition_declarations(
    migrations: tuple[_MigrationDeclaration, ...],
    database_paths: tuple[str, ...],
    transitions: tuple[_LedgerAdvanceTransition, ...],
) -> None:
    transition_clusters = tuple(transition.cluster_through for transition in transitions)
    if transition_clusters != tuple(sorted(set(transition_clusters))):
        raise ValueError("ledger advance transitions must be unique and ordered")
    post_ledger_clusters = {
        entry.path
        for entry in migrations
        if entry.scope == "cluster" and entry.path > "0036_migration_ledger_role.sql"
    }
    if set(transition_clusters) != post_ledger_clusters:
        raise ValueError(
            "every post-ledger cluster migration requires one exact advance transition"
        )
    entries = {entry.path: entry for entry in migrations}
    for transition in transitions:
        _validate_transition_declaration(transition, entries, database_paths)


def _validate_transition_declaration(
    transition: _LedgerAdvanceTransition,
    entries: dict[str, _MigrationDeclaration],
    database_paths: tuple[str, ...],
) -> None:
    _, cluster = _validate_transition_endpoints(
        entries.get(transition.recorded_through),
        entries.get(transition.cluster_through),
    )
    if not hmac.compare_digest(cluster.sha256, transition.cluster_sha256):
        raise ValueError("ledger transition cluster checksum differs from its migration")
    _validate_transition_pending_prefix(transition, database_paths)
    if not (
        transition.recorded_through < transition.cluster_through < transition.pending_database_from
    ):
        raise ValueError("ledger transition is not ordered between database migrations")


def _validate_transition_endpoints(
    recorded: _MigrationDeclaration | None,
    cluster: _MigrationDeclaration | None,
) -> tuple[_MigrationDeclaration, _MigrationDeclaration]:
    if recorded is None or recorded.scope != "database":
        raise ValueError("ledger transition must start from a database migration")
    if cluster is None or cluster.scope != "cluster":
        raise ValueError("ledger transition must bind one cluster migration")
    return recorded, cluster


def _validate_transition_pending_prefix(
    transition: _LedgerAdvanceTransition,
    database_paths: tuple[str, ...],
) -> None:
    try:
        recorded_index = database_paths.index(transition.recorded_through)
        pending_through_index = database_paths.index(transition.pending_database_through)
    except ValueError as error:
        raise ValueError("ledger transition names an unknown database migration") from error
    pending_prefix = database_paths[recorded_index + 1 : pending_through_index + 1]
    if not pending_prefix or pending_prefix[0] != transition.pending_database_from:
        raise ValueError("ledger transition does not bind one contiguous pending prefix")


def _migration_resources() -> Traversable:
    packaged = files("ctower_kernel").joinpath("migrations")
    if packaged.is_dir():
        return packaged
    source_root = Path(__file__).parents[2]
    authored = source_root.parent / "migrations"
    if source_root.name == "src" and authored.is_dir():
        return authored
    raise FileNotFoundError("ctower migration resources are unavailable")


@dataclass(frozen=True, slots=True)
class _LoadedMigrations:
    scripts: tuple[MigrationScript, ...]
    baseline: MigrationBaseline
    ledger_advance_transitions: tuple[MigrationAdvanceTransition, ...] = ()


def _load_migrations() -> _LoadedMigrations:
    resources = _migration_resources()
    manifest = _MigrationManifest.model_validate_json(
        resources.joinpath("manifest.json").read_text(encoding="utf-8")
    )
    declared = tuple(entry.path for entry in manifest.migrations)
    packaged = tuple(
        sorted(
            resource.name
            for resource in resources.iterdir()
            if resource.is_file() and resource.name.endswith(".sql")
        )
    )
    if packaged != declared:
        raise ValueError("migration resource inventory does not match manifest")
    scripts: list[MigrationScript] = []
    for entry in manifest.migrations:
        content = resources.joinpath(entry.path).read_bytes()
        actual = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if not hmac.compare_digest(actual, entry.sha256):
            raise ValueError(f"migration checksum mismatch: {entry.path}")
        scripts.append(MigrationScript(entry.path, entry.sha256, entry.scope, content.decode()))
    baseline = manifest.adoption_baseline
    return _LoadedMigrations(
        tuple(scripts),
        MigrationBaseline(
            baseline.through,
            baseline.schema_sha256,
            baseline.semantic_checks,
            baseline.schema_object_sum256,
        ),
        tuple(
            MigrationAdvanceTransition(
                transition.recorded_through,
                transition.recorded_schema_sha256,
                transition.cluster_through,
                transition.cluster_sha256,
                transition.postgres_major,
                transition.result_schema_sha256,
                transition.schema_object_sum256,
                transition.pending_database_from,
                transition.pending_database_through,
            )
            for transition in manifest.ledger_advance_transitions
        ),
    )


def _migration_scripts(scope: Literal["cluster", "database"]) -> tuple[MigrationScript, ...]:
    return tuple(script for script in _load_migrations().scripts if script.scope == scope)


def _validate_loaded_transition_bindings(loaded: _LoadedMigrations) -> None:
    scripts = {script.migration_id: script for script in loaded.scripts}
    for transition in loaded.ledger_advance_transitions:
        cluster = scripts.get(transition.cluster_through)
        if (
            cluster is None
            or cluster.scope != "cluster"
            or not hmac.compare_digest(cluster.sha256, transition.cluster_sha256)
        ):
            raise MigrationStateError(
                "ledger-transition-declaration-mismatch",
                f"cluster checksum differs for {transition.cluster_through}",
            )


def provision_database_roles(admin_dsn: str) -> None:
    """Serialize and reconcile the cluster-global login/role boundary."""
    with _migration_control_sql.migration_control(admin_dsn):
        _reconcile_database_roles_locked(admin_dsn)


def _reconcile_database_roles_locked(admin_dsn: str) -> None:
    with _migration_control_sql.role_provisioning_control(admin_dsn):
        _migration_control_sql.reconcile_database_roles(admin_dsn, _provision_database_roles_once)


def _provision_database_roles_once(admin_dsn: str) -> None:
    with psycopg.connect(admin_dsn, row_factory=dict_row) as connection:
        validate_recovery_role_shapes(connection)
    probe_preexisting = quarantine_durability_probe(admin_dsn)
    preexisting = _quarantine_projection_runtime(admin_dsn)
    with psycopg.connect(admin_dsn, row_factory=dict_row) as connection:
        if probe_preexisting:
            probe_reasons = probe_role_rejection_reasons(connection, provisioned=False)
            if probe_reasons:
                raise ValueError(
                    f"unsafe pre-existing {DURABILITY_PROBE_ROLE}: {', '.join(probe_reasons)}"
                )
        if preexisting:
            reasons = _projection_role_rejection_reasons(
                connection, require_projection_membership=False, require_login=False
            )
            if reasons:
                raise ValueError(
                    f"unsafe pre-existing {PROJECTION_RUNTIME_ROLE}: {', '.join(reasons)}"
                )
        _apply_cluster_migrations(connection)
        close_durability_probe_boundary(connection)
        probe_reasons = probe_role_rejection_reasons(connection, provisioned=True)
        if probe_reasons:
            raise ValueError(
                f"unsafe provisioned {DURABILITY_PROBE_ROLE}: {', '.join(probe_reasons)}"
            )
        reasons = _projection_role_rejection_reasons(
            connection, require_projection_membership=True, require_login=True
        )
        if reasons:
            raise ValueError(f"unsafe provisioned {PROJECTION_RUNTIME_ROLE}: {', '.join(reasons)}")


def _apply_cluster_migrations(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    for migration in _migration_scripts("cluster"):
        _execute_cluster_migration(connection, migration)


def _execute_cluster_migration(
    connection: psycopg.Connection[dict[str, object]],
    migration: MigrationScript,
) -> None:
    try:
        connection.execute(migration.content)
    except psycopg.errors.RaiseException as error:
        if error.diag.message_primary == RecoveryRoleConfigurationError.MESSAGE:
            raise RecoveryRoleConfigurationError from None
        raise _migration_execution_error(migration.migration_id, error) from None
    except psycopg.Error as error:
        if _migration_control_sql.retryable_database_failure(error):
            raise
        raise _migration_execution_error(migration.migration_id, error) from None


def _quarantine_projection_runtime(admin_dsn: str) -> bool:
    """Commit NOLOGIN before inspecting or attempting to adopt a pre-existing role."""

    with psycopg.connect(admin_dsn, autocommit=True, row_factory=dict_row) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (PROJECTION_RUNTIME_ROLE,)
        ).fetchone()
        if exists is None:
            return False
        connection.execute("ALTER ROLE ctower_projection_runtime NOLOGIN")
        termination_results = connection.execute(
            """
            SELECT pid, pg_catalog.pg_terminate_backend(pid, %s) AS terminated
            FROM pg_stat_activity
            WHERE usename = %s AND pid <> pg_backend_pid()
            ORDER BY pid
            """,
            (PROJECTION_SESSION_TERMINATION_TIMEOUT_MS, PROJECTION_RUNTIME_ROLE),
        ).fetchall()
        unconfirmed = tuple(row for row in termination_results if row["terminated"] is not True)
        if unconfirmed:
            raise RuntimeError(
                f"{PROJECTION_RUNTIME_ROLE} session termination was not confirmed within "
                f"{PROJECTION_SESSION_TERMINATION_TIMEOUT_MS} ms"
            )
        survivor = connection.execute(
            """
            SELECT 1 FROM pg_stat_activity
            WHERE usename = %s AND pid <> pg_backend_pid()
            LIMIT 1
            """,
            (PROJECTION_RUNTIME_ROLE,),
        ).fetchone()
        if survivor is not None:
            raise RuntimeError(f"{PROJECTION_RUNTIME_ROLE} session survived quarantine")
    return True


def _projection_role_rejection_reasons(
    connection: psycopg.Connection[dict[str, object]],
    *,
    require_projection_membership: bool,
    require_login: bool,
) -> tuple[str, ...]:
    role = connection.execute(
        """
        SELECT oid, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit,
            rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname = %s
        """,
        (PROJECTION_RUNTIME_ROLE,),
    ).fetchone()
    if role is None:
        return ("role is absent",)
    reasons = list(_projection_attribute_rejections(role, require_login=require_login))
    reasons.extend(
        _projection_membership_rejections(
            connection,
            role["oid"],
            require_projection_membership=require_projection_membership,
        )
    )
    direct_authority = connection.execute(
        """
        SELECT 1 FROM pg_shdepend
        WHERE refclassid = 'pg_authid'::regclass AND refobjid = %s
          AND deptype IN ('a', 'o')
        LIMIT 1
        """,
        (role["oid"],),
    ).fetchone()
    if direct_authority is not None:
        reasons.append("direct grants or ownership")
    settings = connection.execute(
        "SELECT 1 FROM pg_db_role_setting WHERE setrole = %s LIMIT 1",
        (role["oid"],),
    ).fetchone()
    if settings is not None:
        reasons.append("role settings")
    return tuple(reasons)


def _projection_attribute_rejections(
    role: dict[str, object], *, require_login: bool
) -> tuple[str, ...]:
    login = ("login state",) if bool(role["rolcanlogin"]) is not require_login else ()
    dangerous = any(
        bool(role[name])
        for name in (
            "rolsuper",
            "rolcreatedb",
            "rolcreaterole",
            "rolinherit",
            "rolreplication",
            "rolbypassrls",
        )
    )
    return (*login, *(("dangerous attributes",) if dangerous else ()))


def _projection_membership_rejections(
    connection: psycopg.Connection[dict[str, object]],
    role_id: object,
    *,
    require_projection_membership: bool,
) -> tuple[str, ...]:
    memberships = {
        str(row["rolname"])
        for row in connection.execute(
            """
            WITH RECURSIVE reachable(roleid) AS (
                SELECT membership.roleid
                FROM pg_auth_members AS membership
                WHERE membership.member = %s
                UNION
                SELECT membership.roleid
                FROM pg_auth_members AS membership
                JOIN reachable ON membership.member = reachable.roleid
            )
            SELECT role.rolname
            FROM reachable JOIN pg_roles AS role ON role.oid = reachable.roleid
            """,
            (role_id,),
        ).fetchall()
    }
    expected_memberships = {"ctower_projection"} if require_projection_membership else set()
    closure_safe = (
        memberships == expected_memberships
        if require_projection_membership
        else memberships <= {"ctower_projection"}
    )
    privileged_membership = connection.execute(
        """
        SELECT 1 FROM pg_auth_members
        WHERE member = %s AND admin_option
        LIMIT 1
        """,
        (role_id,),
    ).fetchone()
    closure = () if closure_safe else ("unexpected membership closure",)
    administration = ("membership administration",) if privileged_membership is not None else ()
    return (*closure, *administration)


def apply_migrations(migrator_dsn: str, *, role_admin_dsn: str) -> None:
    """Serialize role reconciliation, application, attestation, and recording."""
    loaded = _load_migrations()
    _validate_loaded_transition_bindings(loaded)
    database_migrations = tuple(m for m in loaded.scripts if m.scope == "database")
    with _migration_control_sql.migration_control(role_admin_dsn) as control:
        upgrade_migration_ledger(control, database_migrations, loaded.baseline)
        _reconcile_database_roles_locked(role_admin_dsn)
        with psycopg.connect(migrator_dsn) as connection:
            connection.execute("SET ROLE ctower_admin")
            pending = apply_database_migrations(
                connection,
                database_migrations,
                loaded.baseline,
                loaded.ledger_advance_transitions,
            )
        # Database migrations can create role-governed functions and grants.
        # Close that boundary before attesting; failure leaves no ledger.
        _reconcile_database_roles_locked(role_admin_dsn)
        record_database_migrations(control, pending, loaded.baseline)


def provision_bootstrap(
    dsn: str,
    *,
    capability_input: TextIO,
    allowed_origin: str,
    expires_at: datetime,
) -> None:
    """Read one capability from a local stream and persist only its digest."""

    capability = capability_input.readline().rstrip("\r\n")
    if len(capability) < MINIMUM_CAPABILITY_LENGTH:
        raise ValueError("bootstrap capability must have at least 32 characters")
    if len(capability) > MAXIMUM_CAPABILITY_LENGTH:
        raise ValueError("bootstrap capability must have at most 256 characters")
    with psycopg.connect(dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        capability_digest = hashlib.sha256(capability.encode("utf-8")).digest()
        connection.execute(
            """
            INSERT INTO bootstrap_capability (
                singleton, capability_digest, allowed_origin, expires_at
            ) VALUES (true, %s, %s, %s)
            ON CONFLICT (singleton) DO UPDATE
            SET expires_at = EXCLUDED.expires_at
            WHERE bootstrap_capability.capability_digest = EXCLUDED.capability_digest
              AND bootstrap_capability.allowed_origin = EXCLUDED.allowed_origin
              AND bootstrap_capability.consumed_at IS NULL
            """,
            (capability_digest, allowed_origin, expires_at),
        )
        stored = connection.execute(
            """
            SELECT capability_digest, host(allowed_origin)
            FROM bootstrap_capability
            WHERE singleton
            """
        ).fetchone()
        if (
            stored is None
            or not hmac.compare_digest(bytes(stored[0]), capability_digest)
            or str(stored[1]) != allowed_origin
        ):
            raise RuntimeError("existing bootstrap capability differs from retry checkpoint")


def provision_principal_credential(
    dsn: str,
    tenant_id: UUID,
    principal_id: UUID,
    *,
    credential_input: TextIO,
) -> None:
    """Bind one runtime credential while persisting only its digest."""

    credential = credential_input.readline().rstrip("\r\n")
    if len(credential) < MINIMUM_CAPABILITY_LENGTH:
        raise ValueError("principal credential must have at least 32 characters")
    if len(credential) > MAXIMUM_CAPABILITY_LENGTH:
        raise ValueError("principal credential must have at most 256 characters")
    now = datetime.now().astimezone()
    credential_digest = hashlib.sha256(credential.encode("utf-8")).digest()
    with psycopg.connect(dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        connection.execute(
            """
            INSERT INTO principal_credentials (
                credential_id, principal_id, tenant_id, credential_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (credential_digest) DO NOTHING
            """,
            (
                _uuid7(now),
                principal_id,
                tenant_id,
                credential_digest,
                now,
            ),
        )
        stored = connection.execute(
            """
            SELECT tenant_id, principal_id, revoked_at
            FROM principal_credentials
            WHERE credential_digest = %s
            """,
            (credential_digest,),
        ).fetchone()
        if stored != (tenant_id, principal_id, None):
            raise RuntimeError("existing principal credential differs from bootstrap retry")


def configure_development_durability(dsn: str) -> None:
    """Select the approved shadow-only ACK policy without making a CP3-D claim."""

    with psycopg.connect(dsn) as connection:
        connection.execute("SET ROLE ctower_admin")
        connection.execute(
            """
            UPDATE durability_policy_state
            SET policy_ref = 'ctower.development-offhost-ack@1',
                mode = 'development_offhost_ack',
                standby_identity = 'ctower_i1_standby',
                configured_at = clock_timestamp()
            WHERE singleton
            """
        )
