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
from psycopg import sql

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


@dataclass(frozen=True, slots=True)
class DurabilityPair:
    """Verifier-owned PostgreSQL 17 primary and physical hot standby."""

    prefix: str
    network: str
    primary_container: str
    standby_container: str
    primary_volume: str
    standby_volume: str
    primary_port: int
    standby_port: int
    primary_admin_dsn: str
    standby_admin_dsn: str


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


def start_durability_pair() -> DurabilityPair:
    """Start one named physical streaming pair without weakening the normal dev database."""

    pair = _new_durability_pair()
    try:
        _docker("network", "create", pair.network)
        _docker("volume", "create", pair.primary_volume)
        _docker("volume", "create", pair.standby_volume)
        _start_durability_primary(pair)
        _clone_durability_standby(pair)
        _launch_durability_standby(pair)
        _enable_named_synchronous_standby(pair)
    except Exception:
        stop_durability_pair(pair)
        raise
    return pair


def _new_durability_pair() -> DurabilityPair:
    prefix = f"ctower-i1-durability-{os.getpid()}-{uuid4().hex[:10]}"
    primary_port, standby_port = _available_port(), _available_port()
    return DurabilityPair(
        prefix=prefix,
        network=f"{prefix}-network",
        primary_container=f"{prefix}-primary",
        standby_container=f"{prefix}-standby",
        primary_volume=f"{prefix}-primary-data",
        standby_volume=f"{prefix}-standby-data",
        primary_port=primary_port,
        standby_port=standby_port,
        primary_admin_dsn=f"postgresql://postgres@127.0.0.1:{primary_port}/ctower",
        standby_admin_dsn=(
            f"postgresql://postgres@127.0.0.1:{standby_port}/ctower?connect_timeout=1"
        ),
    )


def _start_durability_primary(pair: DurabilityPair) -> None:
    _docker(
        "run",
        "-d",
        "--name",
        pair.primary_container,
        "--network",
        pair.network,
        "--network-alias",
        "primary",
        "-p",
        f"127.0.0.1:{pair.primary_port}:5432",
        "-e",
        "POSTGRES_DB=ctower",
        "-e",
        "POSTGRES_HOST_AUTH_METHOD=trust",
        "-e",
        "POSTGRES_USER=postgres",
        "-v",
        f"{pair.primary_volume}:/var/lib/postgresql/data",
        "postgres:17-bookworm",
        "-c",
        "wal_level=replica",
        "-c",
        "max_wal_senders=10",
        "-c",
        "max_replication_slots=10",
        "-c",
        "hot_standby=on",
        "-c",
        "cluster_name=ctower_i1_primary",
    )
    _wait_for_dsn(pair.primary_admin_dsn)
    _enable_fixture_replication(pair)


def _clone_durability_standby(pair: DurabilityPair) -> None:
    _docker(
        "run",
        "--rm",
        "-v",
        f"{pair.standby_volume}:/var/lib/postgresql/data",
        "postgres:17-bookworm",
        "sh",
        "-c",
        ("chown postgres:postgres /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data"),
    )
    slot = f"ctower_i1_{uuid4().hex}"
    _docker(
        "run",
        "--rm",
        "--user",
        "postgres",
        "--network",
        pair.network,
        "-v",
        f"{pair.standby_volume}:/var/lib/postgresql/data",
        "postgres:17-bookworm",
        "pg_basebackup",
        "--dbname=host=primary user=postgres application_name=ctower_i1_ack",
        "--pgdata=/var/lib/postgresql/data",
        "--write-recovery-conf",
        "--wal-method=stream",
        "--create-slot",
        f"--slot={slot}",
    )


def _launch_durability_standby(pair: DurabilityPair) -> None:
    _docker(
        "run",
        "-d",
        "--name",
        pair.standby_container,
        "--network",
        pair.network,
        "-p",
        f"127.0.0.1:{pair.standby_port}:5432",
        "-v",
        f"{pair.standby_volume}:/var/lib/postgresql/data",
        "postgres:17-bookworm",
        "-c",
        "hot_standby=on",
        "-c",
        "cluster_name=ctower_i1_standby",
    )
    _wait_for_dsn(pair.standby_admin_dsn, require_recovery=True)


def stop_durability_pair(pair: DurabilityPair) -> None:
    """Remove only the exact verifier-owned containers, volumes, and network."""

    _docker("rm", "-f", pair.standby_container, pair.primary_container, check=False)
    _docker("volume", "rm", pair.standby_volume, pair.primary_volume, check=False)
    _docker("network", "rm", pair.network, check=False)


@contextmanager
def pause_durability_standby(pair: DurabilityPair) -> Iterator[None]:
    """Freeze the exact standby so authority commits hit their server-side deadline."""

    _docker("pause", pair.standby_container)
    try:
        yield
    finally:
        _docker("unpause", pair.standby_container)
        _wait_for_dsn(pair.standby_admin_dsn, require_recovery=True)
        _wait_for_sync(pair)


@contextmanager
def pause_durability_replay(pair: DurabilityPair) -> Iterator[None]:
    """Pause WAL replay while leaving the receiver and primary sender connected."""

    with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
        connection.execute("SELECT pg_wal_replay_pause()")
    _wait_for_replay_pause(pair, paused=True)
    try:
        yield
    finally:
        with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
            connection.execute("SELECT pg_wal_replay_resume()")
        _wait_for_replay_pause(pair, paused=False)
        _wait_for_replay_current(pair)


@contextmanager
def disconnect_durability_receiver(pair: DurabilityPair) -> Iterator[None]:
    """Restart the standby with an unreachable primary while retaining SQL access."""

    with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
        row = connection.execute("SHOW primary_conninfo").fetchone()
        if row is None:
            raise RuntimeError("standby primary_conninfo was unavailable")
        original = str(row[0])
        connection.execute(
            sql.SQL("ALTER SYSTEM SET primary_conninfo = {}").format(
                sql.Literal("host=127.0.0.1 port=1 user=postgres application_name=ctower_i1_ack")
            )
        )
    _docker("restart", pair.standby_container)
    _wait_for_dsn(pair.standby_admin_dsn, require_recovery=True)
    _wait_for_sender(pair, streaming=False)
    try:
        yield
    finally:
        with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("ALTER SYSTEM SET primary_conninfo = {}").format(sql.Literal(original))
            )
        _docker("restart", pair.standby_container)
        _wait_for_dsn(pair.standby_admin_dsn, require_recovery=True)
        _wait_for_sync(pair)
        _wait_for_replay_current(pair)


@contextmanager
def delay_durability_replay(pair: DurabilityPair) -> Iterator[None]:
    """Create an unpaused, streaming receiver whose replay watermark is behind."""

    with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
        connection.execute("ALTER SYSTEM SET recovery_min_apply_delay = '5s'")
        connection.execute("SELECT pg_reload_conf()")
    try:
        yield
    finally:
        with psycopg.connect(pair.standby_admin_dsn, autocommit=True) as connection:
            connection.execute("ALTER SYSTEM SET recovery_min_apply_delay = '0s'")
            connection.execute("SELECT pg_reload_conf()")
        _wait_for_replay_current(pair)


def create_durability_database(pair: DurabilityPair) -> tuple[DatabaseFixture, str]:
    """Create one primary database and return its replay-only standby DSN."""

    name = f"ctower_test_{uuid4().hex}"
    with psycopg.connect(pair.primary_admin_dsn, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    primary_base = f"127.0.0.1:{pair.primary_port}/{name}"
    standby_dsn = f"postgresql://postgres@127.0.0.1:{pair.standby_port}/{name}?connect_timeout=1"
    _wait_for_dsn(standby_dsn, require_recovery=True)
    return (
        DatabaseFixture(
            name,
            pair.primary_admin_dsn,
            f"postgresql://postgres@{primary_base}",
            f"postgresql://ctower_migrator@{primary_base}",
            f"postgresql://ctower_runtime@{primary_base}",
            f"postgresql://ctower_projection_runtime@{primary_base}",
        ),
        standby_dsn,
    )


def stop_durability_primary(pair: DurabilityPair) -> None:
    """Stop only the verifier-owned primary for host-loss evidence."""

    _docker("stop", pair.primary_container)


def stop_durability_standby(pair: DurabilityPair) -> None:
    """Stop only the verifier-owned standby for a local-only crash boundary."""

    _docker("stop", pair.standby_container)


def start_durability_standby(pair: DurabilityPair) -> None:
    """Restart the exact verifier-owned standby without assuming a live primary."""

    _docker("start", pair.standby_container)
    _wait_for_dsn(pair.standby_admin_dsn, require_recovery=True)


def wait_for_durability_replay_current(pair: DurabilityPair) -> None:
    """Wait until the standby replay watermark reaches the primary flush watermark."""

    _wait_for_replay_current(pair)


def promote_durability_standby(pair: DurabilityPair) -> None:
    """Promote only the verifier-owned standby after the primary is stopped."""

    _docker(
        "exec",
        "--user",
        "postgres",
        pair.standby_container,
        "pg_ctl",
        "promote",
        "-D",
        "/var/lib/postgresql/data",
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(pair.standby_admin_dsn) as connection:
                row = connection.execute("SELECT pg_is_in_recovery()").fetchone()
            if row == (False,):
                return
        except psycopg.OperationalError:
            pass
        time.sleep(0.05)
    raise RuntimeError("promoted standby remained in recovery")


def _enable_named_synchronous_standby(pair: DurabilityPair) -> None:
    with psycopg.connect(pair.primary_admin_dsn, autocommit=True) as connection:
        connection.execute("ALTER SYSTEM SET synchronous_standby_names = 'FIRST 1 (ctower_i1_ack)'")
        connection.execute("SELECT pg_reload_conf()")
    _wait_for_sync(pair)


def _enable_fixture_replication(pair: DurabilityPair) -> None:
    _docker(
        "exec",
        pair.primary_container,
        "sh",
        "-c",
        (
            "printf '%s\\n' 'host replication postgres samenet trust' "
            ">> /var/lib/postgresql/data/pg_hba.conf"
        ),
    )
    with psycopg.connect(pair.primary_admin_dsn, autocommit=True) as connection:
        connection.execute("SELECT pg_reload_conf()")


def _wait_for_sync(pair: DurabilityPair) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with psycopg.connect(pair.primary_admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_stat_replication
                WHERE application_name = 'ctower_i1_ack'
                  AND state = 'streaming' AND sync_state = 'sync'
                """
            ).fetchone()
        if row is not None:
            return
        time.sleep(0.05)
    raise RuntimeError("named standby did not become synchronous")


def _wait_for_replay_pause(pair: DurabilityPair, *, paused: bool) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with psycopg.connect(pair.standby_admin_dsn) as connection:
            row = connection.execute("SELECT pg_is_wal_replay_paused()").fetchone()
        if row == (paused,):
            return
        time.sleep(0.05)
    raise RuntimeError("standby replay did not reach the requested pause state")


def _wait_for_sender(pair: DurabilityPair, *, streaming: bool) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with psycopg.connect(pair.primary_admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT count(*) = 1 AND min(state) = 'streaming'
                FROM pg_stat_replication WHERE application_name = 'ctower_i1_ack'
                """
            ).fetchone()
        if row == (streaming,):
            return
        time.sleep(0.05)
    raise RuntimeError("primary WAL sender did not reach the requested state")


def _wait_for_replay_current(pair: DurabilityPair) -> None:
    """Wait until the standby's own watermark AND the primary's live
    replication-feedback watermark for that standby both reach the primary
    flush watermark.

    ``durability_health()`` (``_durability_health_sql._live_target_failure``)
    requires ``pg_stat_replication.replay_lsn`` -- the PRIMARY's feedback view
    of the standby, refreshed only when the standby's walreceiver next reports
    status -- to have caught up, not only the standby's own directly-queried
    ``pg_last_wal_replay_lsn()``. Waiting on the standby's self-report alone
    leaves a window, wider under a loaded runner, where a caller asserting
    live health immediately after this returns observes a stale
    ``replay_not_current`` (durability_health.py#100's strike) even though the
    standby itself is already current.
    """

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with psycopg.connect(pair.primary_admin_dsn) as primary:
            evidence = primary.execute(
                "SELECT pg_current_wal_flush_lsn()::text,"
                " (SELECT replay_lsn::text FROM pg_stat_replication"
                "  WHERE application_name = 'ctower_i1_ack')"
            ).fetchone()
        with psycopg.connect(pair.standby_admin_dsn) as standby:
            standby_lsn = standby.execute("SELECT pg_last_wal_replay_lsn()::text").fetchone()
        if (
            evidence is not None
            and evidence[0] is not None
            and evidence[1] is not None
            and standby_lsn is not None
            and standby_lsn[0] is not None
            and _lsn_position(str(evidence[1])) >= _lsn_position(str(evidence[0]))
            and _lsn_position(str(standby_lsn[0])) >= _lsn_position(str(evidence[0]))
        ):
            return
        time.sleep(0.05)
    raise RuntimeError("standby replay watermark did not catch the primary flush watermark")


def _lsn_position(value: str) -> int:
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)


def _wait_for_dsn(dsn: str, *, require_recovery: bool = False) -> None:
    deadline = time.monotonic() + 15
    last_error: psycopg.OperationalError | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1) as connection:
                if not require_recovery:
                    return
                row = connection.execute("SELECT pg_is_in_recovery()").fetchone()
                if row == (True,):
                    return
        except psycopg.OperationalError as error:
            last_error = error
        time.sleep(0.05)
    raise RuntimeError(
        "Postgres durability fixture did not reach the required state"
    ) from last_error


def _docker(*arguments: str, check: bool = True) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for Postgres durability tests")

    async def run() -> tuple[int, bytes]:
        process = await asyncio.create_subprocess_exec(
            docker,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        return process.returncode or 0, output

    return_code, output = asyncio.run(run())
    rendered = output.decode(errors="replace")
    if check and return_code != 0:
        raise RuntimeError(f"docker command failed with exit code {return_code}: {rendered}")
    return rendered
