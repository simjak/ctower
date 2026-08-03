"""Isolated PostgreSQL 17 fixture mechanics for migration threat tests."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
COMPOSE = ROOT / "deploy/development/compose.yaml"


@dataclass(frozen=True, slots=True)
class Database:
    admin_dsn: str
    migrator_dsn: str
    runtime_dsn: str
    projection_dsn: str
    tenant_id: UUID
    operator_id: UUID
    commander_id: UUID


def isolated_database() -> Iterator[Database]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for PostgreSQL migration tests")
    port = _available_port()
    project = f"ctower-migration-{os.getpid()}-{uuid4().hex[:10]}"
    environment = {**os.environ, "CTOWER_POSTGRES_PORT": str(port)}
    command = [docker, "compose", "-p", project, "-f", str(COMPOSE)]
    _compose(command, environment, "up", "-d")
    cluster_dsn = f"postgresql://postgres@127.0.0.1:{port}/ctower"
    database_name = f"ctower_migration_{uuid4().hex}"
    try:
        _wait_for_postgres(cluster_dsn)
        provision_database_roles(cluster_dsn)
        with psycopg.connect(cluster_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        base = f"127.0.0.1:{port}/{database_name}"
        yield _setup_database(
            f"postgresql://postgres@{base}",
            f"postgresql://ctower_migrator@{base}",
            f"postgresql://ctower_runtime@{base}",
            f"postgresql://ctower_projection_runtime@{base}",
        )
    finally:
        with psycopg.connect(cluster_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
        _compose(command, environment, "down", "--volumes")


@contextmanager
def isolated_fresh_database_pair() -> Iterator[tuple[str, str]]:
    """Yield two unprovisioned databases in one disposable PostgreSQL cluster."""

    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for PostgreSQL migration tests")
    port = _available_port()
    project = f"ctower-role-race-{os.getpid()}-{uuid4().hex[:10]}"
    environment = {**os.environ, "CTOWER_POSTGRES_PORT": str(port)}
    command = [docker, "compose", "-p", project, "-f", str(COMPOSE)]
    cluster_dsn = f"postgresql://postgres@127.0.0.1:{port}/ctower"
    database_names = (
        f"ctower_role_a_{uuid4().hex}",
        f"ctower_role_b_{uuid4().hex}",
    )
    try:
        _compose(command, environment, "up", "-d")
        _wait_for_postgres(cluster_dsn)
        with psycopg.connect(cluster_dsn, autocommit=True) as connection:
            for database_name in database_names:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
                )
        yield (
            f"postgresql://postgres@127.0.0.1:{port}/{database_names[0]}",
            f"postgresql://postgres@127.0.0.1:{port}/{database_names[1]}",
        )
    finally:
        _compose(command, environment, "down", "--volumes")


def semantic_counts(database: Database) -> tuple[int, ...]:
    tables = (
        "tickets",
        "ticket_relations",
        "events",
        "outbox",
        "command_results",
        "migration_import_batches",
        "migration_import_operation_results",
        "migration_alias_revisions",
        "migration_source_link_revisions",
        "migration_relation_validity_facts",
        "migration_corrections",
        "migration_reconciliation_facts",
        "migration_fence_observations",
        "migration_verified_artifacts",
        "migration_import_plans",
        "migration_import_plan_batches",
        "migration_import_replay_receipts",
        "migration_fence_registries",
        "migration_fence_observer_bindings",
    )
    with psycopg.connect(database.admin_dsn) as connection:
        counts: list[int] = []
        for table in tables:
            row = connection.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()
            if row is None:
                raise RuntimeError(f"count unavailable for {table}")
            counts.append(int(row[0]))
        position_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        if position_row is None:
            raise RuntimeError("record position ledger is unavailable")
        position = int(position_row[0])
    return (*counts, position)


def relation_digest(database: Database, relation_id: UUID) -> str:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT semantic_digest FROM migration_relation_validity_facts
            WHERE relation_id = %s ORDER BY revision DESC LIMIT 1
            """,
            (relation_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("relation validity fact is unavailable")
    return f"sha256:{bytes(row[0]).hex()}"


def alias_digest(database: Database, alias_id: UUID) -> str:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT semantic_digest FROM migration_alias_revisions
            WHERE alias_id = %s ORDER BY revision DESC LIMIT 1
            """,
            (alias_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("alias revision is unavailable")
    return f"sha256:{bytes(row[0]).hex()}"


def source_link_digest(database: Database, link_id: UUID) -> str:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT semantic_digest FROM migration_source_link_revisions
            WHERE link_id = %s ORDER BY revision DESC LIMIT 1
            """,
            (link_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("source-link revision is unavailable")
    return f"sha256:{bytes(row[0]).hex()}"


def add_fence_observer(database: Database) -> Actor:
    observer_id = uuid4()
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'fence_observer', 'Synthetic Fence Observer', false, %s)
            """,
            (observer_id, database.tenant_id, datetime.now(UTC)),
        )
    return Actor(observer_id, database.tenant_id, PrincipalKind.FENCE_OBSERVER)


def _setup_database(
    admin_dsn: str,
    migrator_dsn: str,
    runtime_dsn: str,
    projection_dsn: str,
) -> Database:
    provision_database_roles(admin_dsn)
    apply_migrations(migrator_dsn, role_admin_dsn=admin_dsn)
    now = datetime.now(UTC)
    tenant_id, operator_id, commander_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
            (tenant_id, "ctower", "Ctower", now),
        )
        connection.cursor().executemany(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, %s, %s, false, %s)
            """,
            (
                (operator_id, tenant_id, "operator", "Migration Operator", now),
                (commander_id, tenant_id, "commander", "Ctower Commander", now),
            ),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                tenant_id, project_key, seat_key, principal_id, granted_by, granted_at
            ) VALUES (%s, 'ctower', 'commander', %s, %s, %s)
            """,
            (tenant_id, commander_id, operator_id, now),
        )
    return Database(
        admin_dsn,
        migrator_dsn,
        runtime_dsn,
        projection_dsn,
        tenant_id,
        operator_id,
        commander_id,
    )


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _compose(command: list[str], environment: dict[str, str], *arguments: str) -> None:
    asyncio.run(_compose_async(command, environment, *arguments))


async def _compose_async(command: list[str], environment: dict[str, str], *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        *arguments,
        cwd=ROOT,
        env=environment,
    )
    if await process.wait() != 0:
        raise RuntimeError("docker compose failed")


def _wait_for_postgres(dsn: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1):
                return
        except psycopg.OperationalError:
            time.sleep(0.05)
    raise RuntimeError("PostgreSQL did not start within fifteen seconds")
