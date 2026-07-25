"""Real installed-wheel bootstrap and control-worker smoke support."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg

__all__ = ["run_installed_bootstrap_smoke"]

EXIT_TEMPORARY = 75
_PROVISION = """
import os
import sys
from datetime import UTC, datetime, timedelta
from ctower_kernel.record.postgres import (
    apply_migrations,
    provision_bootstrap,
    provision_database_roles,
)
provision_database_roles(os.environ["CTOWER_ADMIN_DSN"])
apply_migrations(
    os.environ["CTOWER_MIGRATOR_DSN"],
    role_admin_dsn=os.environ["CTOWER_ADMIN_DSN"],
)
provision_bootstrap(
    os.environ["CTOWER_MIGRATOR_DSN"],
    capability_input=sys.stdin,
    allowed_origin="127.0.0.1",
    expires_at=datetime.now(UTC) + timedelta(minutes=5),
)
"""
_API = """
import os
import uvicorn
from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord
uvicorn.run(
    create_app(PostgresRecord(os.environ["CTOWER_RUNTIME_DSN"])),
    host="127.0.0.1",
    port=int(os.environ["CTOWER_API_PORT"]),
    access_log=False,
    log_config=None,
    log_level="critical",
)
"""
_WORKER = """
import json
import os
from pathlib import Path
import ctower_kernel
from ctower_api._outbox_loop import OutboxLoop
from ctower_api._project_delivery_loop import ProjectDeliveryLoop
from ctower_api._routine_loop import RoutineLoop
from ctower_api.control_worker import ControlWorker
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.postgres import PostgresRuntime
runtime = Routine(PostgresRuntime(os.environ["CTOWER_RUNTIME_DSN"]))
projections = Projections(PostgresProjections(os.environ["CTOWER_PROJECTION_DSN"]))
ControlWorker(
    runtime,
    RoutineLoop(runtime, ()),
    OutboxLoop(projections),
    ProjectDeliveryLoop(projections),
).tick()
print(json.dumps({
    "kernel_path": str(Path(ctower_kernel.__file__).resolve()),
    "tenant_count": len(runtime.tenant_ids()),
}))
"""


@dataclass(frozen=True, slots=True)
class _Database:
    admin_dsn: str
    migrator_dsn: str
    runtime_dsn: str
    projection_dsn: str


def run_installed_bootstrap_smoke(
    *,
    binary_directory: Path,
    environment: Mapping[str, str],
    outside_checkout: Path,
) -> dict[str, object]:
    """Exercise installed migrations, API, CLI bootstrap, and one worker tick."""

    with _postgres() as database:
        process_environment = _database_environment(environment, database)
        capability = secrets.token_urlsafe(32)
        _checked(
            (binary_directory / "python", "-I", "-c", _PROVISION),
            environment=process_environment,
            cwd=outside_checkout,
            stdin=f"{capability}\n",
        )
        port = _unused_port()
        process_environment["CTOWER_API_PORT"] = str(port)
        with _api_server(
            binary_directory,
            process_environment,
            outside_checkout,
            port,
        ):
            bootstrap = _run(
                _bootstrap_command(binary_directory, port),
                environment=process_environment,
                cwd=outside_checkout,
                stdin=f"{capability}\n",
            )
        worker = _checked(
            (binary_directory / "python", "-I", "-c", _WORKER),
            environment=process_environment,
            cwd=outside_checkout,
        )
    return {
        "bootstrap": json.loads(bootstrap.stdout),
        "bootstrap_status": bootstrap.returncode,
        "worker": json.loads(worker.stdout),
    }


def _database_environment(
    environment: Mapping[str, str],
    database: _Database,
) -> dict[str, str]:
    configured = dict(environment)
    configured.update(
        {
            "CTOWER_ADMIN_DSN": database.admin_dsn,
            "CTOWER_MIGRATOR_DSN": database.migrator_dsn,
            "CTOWER_PROJECTION_DSN": database.projection_dsn,
            "CTOWER_RUNTIME_DSN": database.runtime_dsn,
        }
    )
    return configured


def _bootstrap_command(binary_directory: Path, port: int) -> tuple[str | Path, ...]:
    return (
        binary_directory / "ctl",
        "--base-url",
        f"http://127.0.0.1:{port}",
        "bootstrap",
        "first-tenant",
        "--command-id",
        str(uuid4()),
        "--tenant-name",
        "Installed Wheel Tenant",
        "--tenant-slug",
        "installed-wheel",
        "--operator-name",
        "Installed Wheel Operator",
        "--operator-credential-ref",
        "credential-ref:installed-wheel/operator",
        "--operator-vault-ref",
        "vault-ref:installed-wheel/operator",
        "--commander-name",
        "Installed Wheel Commander",
        "--commander-vault-ref",
        "vault-ref:installed-wheel/commander",
    )


@contextmanager
def _postgres() -> Iterator[_Database]:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for the installed bootstrap smoke")
    port = _unused_port()
    container = f"ctower-wheel-{os.getpid()}-{uuid4().hex[:10]}"
    started = _system_run(
        (
            docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{port}:5432",
            "--env",
            "POSTGRES_DB=ctower",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            "POSTGRES_USER=postgres",
            "postgres:17-bookworm",
        ),
        timeout=60,
    )
    if started.returncode != 0:
        raise RuntimeError(started.stdout + started.stderr)
    try:
        admin_dsn = f"postgresql://postgres@127.0.0.1:{port}/ctower"
        _wait_for_database(admin_dsn)
        yield _Database(
            admin_dsn=admin_dsn,
            migrator_dsn=f"postgresql://ctower_migrator@127.0.0.1:{port}/ctower",
            runtime_dsn=f"postgresql://ctower_runtime@127.0.0.1:{port}/ctower",
            projection_dsn=(f"postgresql://ctower_projection_runtime@127.0.0.1:{port}/ctower"),
        )
    finally:
        _system_run(
            (docker, "stop", "--time", "5", container),
            timeout=15,
        )


def _wait_for_database(dsn: str) -> None:
    deadline = time.monotonic() + 15
    last_error: psycopg.OperationalError | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1):
                return
        except psycopg.OperationalError as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError("installed-wheel Postgres did not start") from last_error


@contextmanager
def _api_server(
    binary_directory: Path,
    environment: Mapping[str, str],
    cwd: Path,
    port: int,
) -> Iterator[None]:
    process_environment = _command_environment(
        (binary_directory / "python", "-I", "-c", _API),
        environment,
    )
    process = subprocess.Popen(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        cwd=cwd,
        env=process_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for_api(process, port)
    try:
        yield
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def _wait_for_api(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + 10
    while process.poll() is None and time.monotonic() < deadline:
        with socket.socket() as candidate:
            if candidate.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.02)
    stdout, stderr = process.communicate(timeout=5)
    raise RuntimeError(f"installed API did not start: {stdout}{stderr}")


def _checked(
    command: Sequence[str | Path],
    *,
    environment: Mapping[str, str],
    cwd: Path,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = _run(command, environment=environment, cwd=cwd, stdin=stdin)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def _run(
    command: Sequence[str | Path],
    *,
    environment: Mapping[str, str],
    cwd: Path,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process_environment = _command_environment(command, environment)
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        cwd=cwd,
        env=process_environment,
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _system_run(
    command: Sequence[str | Path],
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    process_environment = _command_environment(command, os.environ)
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        env=process_environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _command_environment(
    command: Sequence[str | Path],
    environment: Mapping[str, str],
) -> dict[str, str]:
    process_environment = dict(environment)
    process_environment["CTOWER_TEST_COMMAND"] = json.dumps(
        tuple(str(argument) for argument in command)
    )
    return process_environment


def _unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return cast(int, candidate.getsockname()[1])
