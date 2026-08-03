"""One throwaway migrated cluster the checkpoint verbs are allowed to destroy."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from modules.migration._postgres import (
    COMPOSE,
    _available_port,
    _compose,
    _wait_for_postgres,
)

from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

__all__ = ["DisposableInstance", "disposable_cluster"]


@dataclass(frozen=True, slots=True)
class DisposableInstance:
    """The container name and administrator DSN of one disposable cluster."""

    container: str
    admin_dsn: str


def disposable_cluster() -> Iterator[DisposableInstance]:
    """Start, migrate, and afterwards delete one single-container PostgreSQL 17 cluster."""

    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is required for development checkpoint round-trip tests")
    port = _available_port()
    project = f"ctower-checkpoint-{os.getpid()}-{uuid4().hex[:10]}"
    environment = {**os.environ, "CTOWER_POSTGRES_PORT": str(port)}
    command = [docker, "compose", "-p", project, "-f", str(COMPOSE)]
    admin_dsn = f"postgresql://postgres@127.0.0.1:{port}/ctower"
    try:
        _compose(command, environment, "up", "-d")
        _wait_for_postgres(admin_dsn)
        provision_database_roles(admin_dsn)
        apply_migrations(
            f"postgresql://ctower_migrator@127.0.0.1:{port}/ctower",
            role_admin_dsn=admin_dsn,
        )
        yield DisposableInstance(container=f"{project}-postgres-1", admin_dsn=admin_dsn)
    finally:
        _compose(command, environment, "down", "--volumes")
