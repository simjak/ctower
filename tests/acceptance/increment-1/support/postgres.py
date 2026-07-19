"""Ephemeral database lifecycle for real Record-tier acceptance tests."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).parents[4]
COMPOSE = ROOT / "deploy/development/compose.yaml"
PROJECT = "ctower-i1-tests"
ADMIN_DSN = "postgresql://postgres@127.0.0.1:55432/ctower"

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatabaseFixture:
    """One isolated Postgres database and its password-free development DSN."""

    name: str
    dsn: str


def start_postgres() -> None:
    """Start the authored Postgres 17 development composition."""

    asyncio.run(
        _compose(
            "up",
            "-d",
            "--wait",
        )
    )


def stop_postgres() -> None:
    """Remove the acceptance composition and its ephemeral volume."""

    asyncio.run(_compose("down", "--volumes"))


async def _compose(*arguments: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for Postgres acceptance tests")
    process = await asyncio.create_subprocess_exec(
        docker,
        "compose",
        "-p",
        PROJECT,
        "-f",
        str(COMPOSE),
        *arguments,
        cwd=ROOT,
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError(f"docker compose failed with exit code {return_code}")


def create_database() -> DatabaseFixture:
    """Create one isolated database for a test."""

    name = f"ctower_test_{uuid4().hex}"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    return DatabaseFixture(name, f"postgresql://postgres@127.0.0.1:55432/{name}")


def drop_database(database: DatabaseFixture) -> None:
    """Drop one isolated database even after a failed test connection."""

    with psycopg.connect(ADMIN_DSN, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{database.name}" WITH (FORCE)')
