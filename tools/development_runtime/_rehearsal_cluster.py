"""One disposable PostgreSQL 17 cluster on tmpfs and ref-bound source trees."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg

from ctower_api.development_config import load_config
from tools.development_runtime._rehearsal_vocabulary import (
    BASE_REF_SEARCH_DEPTH,
    COMPOSE_PROJECT_PREFIX,
    DATABASE_NAME,
    MANIFEST_RELATIVE,
    REPO_ROOT,
    UpgradeRehearsalError,
)
from tools.development_runtime.host_commands import docker_path

__all__ = [
    "Clone",
    "describe_source",
    "disposable_cluster",
    "resolve_base_ref",
    "source_tree",
]


@dataclass(frozen=True, slots=True)
class Clone:
    container: str
    project: str
    port: int
    admin_dsn: str
    migrator_dsn: str


@contextmanager
def disposable_cluster(
    compose_file: Path,
    forbidden_ports: set[int],
    *,
    keep: bool,
) -> Iterator[Clone]:
    """Yield one tmpfs PostgreSQL 17 cluster on a port that cannot be live's."""

    docker = docker_path()
    port = _free_port(forbidden_ports)
    project = f"{COMPOSE_PROJECT_PREFIX}{uuid.uuid4().hex[:10]}"
    environment = {**os.environ, "CTOWER_POSTGRES_PORT": str(port)}
    compose = [docker, "compose", "-p", project, "-f", str(compose_file)]
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [*compose, "up", "-d"], env=environment, check=True, capture_output=True
    )
    try:
        base = f"127.0.0.1:{port}/{DATABASE_NAME}"
        clone = Clone(
            container=f"{project}-postgres-1",
            project=project,
            port=port,
            admin_dsn=f"postgresql://postgres@{base}",
            migrator_dsn=f"postgresql://ctower_migrator@{base}",
        )
        _wait_for_postgres(clone.admin_dsn)
        yield clone
    finally:
        if keep:
            print(f"    kept disposable cluster {project} on 127.0.0.1:{port}")
        else:
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [*compose, "down", "--volumes"],
                env=environment,
                capture_output=True,
                check=False,
            )


def _free_port(forbidden: set[int]) -> int:
    for _ in range(20):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        if port not in forbidden:
            return port
    raise UpgradeRehearsalError("could not find a port that is not the live instance")


def _wait_for_postgres(dsn: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1):
                return
        except psycopg.OperationalError:
            time.sleep(0.1)
    raise UpgradeRehearsalError("the disposable PostgreSQL did not accept connections within 30s")


@contextmanager
def source_tree(
    ref: str | None,
    path: Path | None,
    run_root: Path,
    label: str,
) -> Iterator[Path]:
    """Yield an existing checkout or a temporary detached worktree for one ref."""

    if path is not None:
        yield path.resolve()
        return
    git = _git_path()
    destination = run_root / label
    subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
        [
            git,
            "-C",
            str(REPO_ROOT),
            "worktree",
            "add",
            "--detach",
            str(destination),
            ref or "HEAD",
        ],
        check=True,
        capture_output=True,
    )
    try:
        yield destination
    finally:
        subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
            [git, "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(destination)],
            capture_output=True,
            check=False,
        )


def resolve_base_ref(terminal_migration: str) -> str:
    """Return the newest commit whose manifest ends where the live ledger ends."""

    git = _git_path()
    listed = subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
        [git, "-C", str(REPO_ROOT), "rev-list", "origin/main", "--", str(MANIFEST_RELATIVE)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    for commit in listed[:BASE_REF_SEARCH_DEPTH]:
        blob = subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
            [git, "-C", str(REPO_ROOT), "show", f"{commit}:{MANIFEST_RELATIVE}"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        try:
            baseline = json.loads(blob)["adoption_baseline"]["through"]
        except (json.JSONDecodeError, KeyError):
            continue
        if baseline == terminal_migration:
            return str(commit)
    raise UpgradeRehearsalError(
        f"no ctower commit carries a manifest terminating at {terminal_migration}; "
        "the live ledger position cannot be reconstructed"
    )


def describe_source(path: Path, ref: str | None) -> str:
    git = _git_path()
    head = subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
        [git, "-C", str(path), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
        [git, "-C", str(path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    suffix = " +uncommitted" if dirty else ""
    return f"{ref or path}@{head}{suffix}"


def _live_ports(*, offline: bool) -> set[int]:
    if offline:
        return set()
    config = load_config()
    return {config.primary_port, config.standby_port}


def _prune_docker_networks() -> None:
    docker = docker_path()
    subprocess.run(  # noqa: S603 - resolved executable, fixed argv, no shell
        [docker, "network", "prune", "-f"], check=True, capture_output=True
    )


def _git_path() -> str:
    git = shutil.which("git")
    if git is None:
        raise UpgradeRehearsalError("git is required for ref-bound rehearsal source trees")
    return git
