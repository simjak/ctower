"""Network-isolated initialization of the E2 PostgreSQL primary."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from ctower_api.development_config import DevelopmentConfig, load_secret

__all__ = ["start_primary"]

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_NETWORK = "ctower-development-network"
_PRIMARY = "ctower-development-primary"
_INITIALIZER = "ctower-development-primary-initializer"
_PRIMARY_VOLUME = "ctower-development-primary-data"
_ATTACH_SECONDS = 1.0


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
    result = subprocess.run(  # noqa: S603 - exact local container inspection
        [_docker_path(), "container", "inspect", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _container_state(name: str) -> str:
    return _docker("inspect", "--format={{.State.Status}}", name).strip()


def _container_database_ready() -> bool:
    result = subprocess.run(  # noqa: S603 - exact local container probe
        [_docker_path(), "exec", _INITIALIZER, "pg_isready", "-U", "postgres"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
        result = subprocess.run(  # noqa: S603 - fixed Docker attach operation
            [_docker_path(), "attach", "--sig-proxy=false", _INITIALIZER],
            check=False,
            input=value,
            capture_output=True,
            text=True,
            timeout=_ATTACH_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return
    if result.returncode:
        raise RuntimeError("Docker refused the bounded initialization attachment")
    raise RuntimeError("PostgreSQL container exited during secret initialization")


def _docker(*arguments: str) -> str:
    result = subprocess.run(  # noqa: S603 - closed lifecycle arguments
        [_docker_path(), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _docker_path() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for the persistent development database")
    return str(Path(docker).resolve(strict=True))
