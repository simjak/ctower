"""Network-isolated initialization of the E2 PostgreSQL primary."""

from __future__ import annotations

import time

import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import DevelopmentConfig
from ctower_api.development_secrets import load_secret
from tools.development_runtime.host_commands import docker_path

__all__ = ["start_primary"]

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_NETWORK = "ctower-development-network"
_PRIMARY = "ctower-development-primary"
_INITIALIZER = "ctower-development-primary-initializer"
_PRIMARY_VOLUME = "ctower-development-primary-data"
_ATTACH_SECONDS = 1.0
_INSPECT_TIMEOUT_SECONDS = 10.0
_LIFECYCLE_TIMEOUT_SECONDS = 120.0


def start_primary(config: DevelopmentConfig) -> None:
    """Initialize the volume without a network, then start the published primary."""

    _initialize_volume(config)
    _run_primary(config)


def _initialize_volume(config: DevelopmentConfig) -> None:
    if not _container_exists(_INITIALIZER):
        _docker(
            "create",
            "-i",
            "--pull",
            "never",
            "--name",
            _INITIALIZER,
            "--network",
            "none",
            "-e",
            "POSTGRES_DB=ctower",
            "-e",
            "POSTGRES_PASSWORD_FILE=/dev/stdin",
            "-e",
            "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
            "-e",
            "POSTGRES_USER=postgres",
            "-v",
            f"{_PRIMARY_VOLUME}:/var/lib/postgresql/data",
            _IMAGE,
        )
    if _container_state(_INITIALIZER) != "running":
        _docker("start", _INITIALIZER)
    if not _container_database_ready():
        _attach_container_input(load_secret(config.postgres_admin_secret_ref))
    _wait_for_database()
    _docker("stop", "--time", "30", _INITIALIZER)
    _docker("rm", _INITIALIZER)


def _run_primary(config: DevelopmentConfig) -> None:
    _docker(
        "run",
        "-d",
        "--pull",
        "never",
        "--restart",
        "unless-stopped",
        "--name",
        _PRIMARY,
        "--network",
        _NETWORK,
        "--network-alias",
        "primary",
        "-p",
        f"127.0.0.1:{config.primary_port}:5432",
        "-v",
        f"{_PRIMARY_VOLUME}:/var/lib/postgresql/data",
        _IMAGE,
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


def _container_exists(name: str) -> bool:
    result = process_execution.run(
        [docker_path(), "container", "inspect", name],
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
        check=False,
        discard_output=True,
    )
    return result.returncode == 0


def _container_state(name: str) -> str:
    return _docker("inspect", "--format={{.State.Status}}", name).strip()


def _container_database_ready() -> bool:
    result = process_execution.run(
        [docker_path(), "exec", _INITIALIZER, "pg_isready", "-U", "postgres"],
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
        check=False,
        discard_output=True,
    )
    return result.returncode == 0


def _wait_for_database() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _container_database_ready():
            return
        time.sleep(0.1)
    raise RuntimeError("development PostgreSQL initializer did not become ready")


def _attach_container_input(value: str) -> None:
    try:
        result = process_execution.run(
            [docker_path(), "attach", "--sig-proxy=false", _INITIALIZER],
            timeout_seconds=_ATTACH_SECONDS,
            check=False,
            input_text=value,
            capture_output=True,
        )
    except process_execution.ProcessTimeoutError:
        return
    if result.returncode:
        raise RuntimeError("Docker refused the bounded initialization attachment")
    raise RuntimeError("PostgreSQL container exited during secret initialization")


def _docker(*arguments: str) -> str:
    result = process_execution.run(
        [docker_path(), *arguments],
        timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
    )
    return result.stdout or ""
