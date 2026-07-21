"""Ephemeral database lifecycle for real Record-tier acceptance tests."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).parents[4]
COMPOSE = ROOT / "deploy/development/compose.yaml"

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatabaseFixture:
    """One isolated database with distinct administration, migration, and runtime DSNs."""

    name: str
    cluster_dsn: str
    admin_dsn: str
    migrator_dsn: str
    runtime_dsn: str
    projection_dsn: str


@dataclass(frozen=True, slots=True)
class PostgresServer:
    """One verifier-owned Compose project on a collision-safe loopback port."""

    project: str
    port: int
    admin_dsn: str


def start_postgres() -> PostgresServer:
    """Start the authored Postgres 17 development composition."""

    port = _available_port()
    server = PostgresServer(
        project=f"ctower-i1-{os.getpid()}-{uuid4().hex[:12]}",
        port=port,
        admin_dsn=f"postgresql://postgres@127.0.0.1:{port}/ctower",
    )
    try:
        asyncio.run(
            _compose(
                server,
                "up",
                "-d",
            )
        )
        _wait_for_postgres(server)
    except Exception:
        asyncio.run(_compose(server, "down", "--volumes"))
        raise
    return server


def _wait_for_postgres(server: PostgresServer) -> None:
    """Require a real SQL connection after the container health transition."""

    deadline = time.monotonic() + 10
    last_error: psycopg.OperationalError | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(server.admin_dsn, connect_timeout=1):
                return
        except psycopg.OperationalError as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError("Postgres did not accept SQL connections within ten seconds") from last_error


def stop_postgres(server: PostgresServer) -> None:
    """Remove only one verifier-owned composition and its ephemeral volume."""

    asyncio.run(_compose(server, "down", "--volumes"))


@contextmanager
def suspend_postgres_backend(server: PostgresServer, pid: int) -> Iterator[None]:
    """Pause one exact backend so timed termination deterministically cannot complete."""

    asyncio.run(
        _compose(server, "exec", "-T", "postgres", "sh", "-c", 'kill -STOP "$1"', "sh", str(pid))
    )
    try:
        yield
    finally:
        asyncio.run(
            _compose(
                server,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'kill -CONT "$1"',
                "sh",
                str(pid),
            )
        )


async def _compose(server: PostgresServer, *arguments: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for Postgres acceptance tests")
    process = await asyncio.create_subprocess_exec(
        docker,
        "compose",
        "-p",
        server.project,
        "-f",
        str(COMPOSE),
        *arguments,
        cwd=ROOT,
        env={**os.environ, "CTOWER_POSTGRES_PORT": str(server.port)},
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError(f"docker compose failed with exit code {return_code}")


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def create_database(server: PostgresServer) -> DatabaseFixture:
    """Create one isolated database for a test."""

    name = f"ctower_test_{uuid4().hex}"
    with psycopg.connect(server.admin_dsn, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    base = f"127.0.0.1:{server.port}/{name}"
    return DatabaseFixture(
        name,
        server.admin_dsn,
        f"postgresql://postgres@{base}",
        f"postgresql://ctower_migrator@{base}",
        f"postgresql://ctower_runtime@{base}",
        f"postgresql://ctower_projection_runtime@{base}",
    )


def drop_database(database: DatabaseFixture) -> None:
    """Drop one isolated database even after a failed test connection."""

    with psycopg.connect(database.cluster_dsn, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{database.name}" WITH (FORCE)')
