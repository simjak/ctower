"""Unprivileged operations tooling for the approved E2 persistent shadow instance."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import (
    DevelopmentConfig,
    config_path,
    load_config,
    load_state,
    write_config,
)
from ctower_api.development_finalizer import observe_finalizer_health
from ctower_api.development_secrets import (
    SecretReferenceMissingError,
    development_dsn,
    load_secret,
    put_secret,
    unlock_development_keyring,
)
from ctower_kernel.record.postgres import (
    PostgresRecord,
    apply_migrations,
    configure_development_durability,
    provision_database_roles,
)
from ctowerctl.discovery import CliInstanceCatalog, write_catalog
from tools.development_runtime._postgres_scram import postgres_scram_verifier
from tools.development_runtime.bootstrap import bootstrap_instance
from tools.development_runtime.checkpoint import (
    add_checkpoint_commands,
    run_checkpoint_command,
)
from tools.development_runtime.host_commands import docker_path, unit_state
from tools.development_runtime.installation import (
    install_runtime,
    rollback_runtime,
    runtime_home,
)
from tools.development_runtime.primary import start_primary

__all__ = ["keyring_unlock_main", "main"]

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_NETWORK = "ctower-development-network"
_SUBNET = "10.253.216.0/24"
_PRIMARY = "ctower-development-primary"
_STANDBY = "ctower-development-ack"
_STANDBY_CLONE = "ctower-development-ack-clone"
_STANDBY_PREPARER = "ctower-development-ack-volume-preparer"
_PRIMARY_VOLUME = "ctower-development-primary-data"
_STANDBY_VOLUME = "ctower-development-ack-data"
_SECRET_REFS = {
    "postgres_admin_secret_ref": "secret-service:ctower-development/postgres-admin",
    "migrator_secret_ref": "secret-service:ctower-development/migrator",
    "runtime_secret_ref": "secret-service:ctower-development/runtime",
    "projection_secret_ref": "secret-service:ctower-development/projection",
    "operator_secret_ref": "secret-service:ctower-development/operator",
    "commander_secret_ref": "secret-service:ctower-development/commander",
}
_HBA = """local all all trust
host replication postgres 10.253.216.0/24 scram-sha-256
host all all 0.0.0.0/0 scram-sha-256
host all all ::/0 scram-sha-256
"""
_INSPECT_TIMEOUT_SECONDS = 10.0
_LIFECYCLE_TIMEOUT_SECONDS = 120.0
_SYSTEMD_TIMEOUT_SECONDS = 60.0


def main() -> None:
    """Execute one bounded persistent-runtime operation."""

    arguments = _parser().parse_args()
    match arguments.command:
        case "database-up":
            database_up()
        case "install-units":
            install_units(arguments.unit_root)
        case "bootstrap":
            bootstrap_instance(arguments.tenant_name, arguments.tenant_slug)
        case "install-runtime":
            install_runtime(
                arguments.wheel,
                arguments.manifest,
                arguments.packs,
                arguments.python,
                arguments.source_root,
                replace=arguments.replace,
            )
        case "rollback-runtime":
            rollback_runtime()
        case "expose-cli":
            print(json.dumps(expose_cli(), sort_keys=True))
        case "checkpoint" | "restore":
            print(run_checkpoint_command(arguments))
        case _:
            print(json.dumps(observe(), sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctower-private-vps")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("database-up")
    units = commands.add_parser("install-units")
    units.add_argument("--unit-root", type=Path, required=True)
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--tenant-name", default="Ctower Development")
    bootstrap.add_argument("--tenant-slug", default="ctower-development")
    installation = commands.add_parser("install-runtime")
    installation.add_argument("--wheel", type=Path, required=True)
    installation.add_argument("--manifest", type=Path, required=True)
    installation.add_argument("--packs", type=Path, required=True)
    installation.add_argument("--python", type=Path, required=True)
    installation.add_argument("--source-root", type=Path, required=True)
    installation.add_argument("--replace", action="store_true")
    commands.add_parser("rollback-runtime")
    commands.add_parser("expose-cli")
    add_checkpoint_commands(commands)
    commands.add_parser("observe")
    return parser


def database_up() -> None:
    """Create or restart the fixed persistent PostgreSQL 17 ACK pair."""

    primary_exists = _container_exists(_PRIMARY)
    standby_exists = _container_exists(_STANDBY)
    if primary_exists != standby_exists:
        raise RuntimeError("incomplete development database pair requires operator recovery")
    config = _ensure_config_and_secrets(create_missing=not primary_exists)
    if primary_exists:
        _restart_database(config)
        return
    _create_database(config)


def _restart_database(config: DevelopmentConfig) -> None:
    _docker("start", _PRIMARY, _STANDBY)
    admin_dsn = development_dsn(config, "postgres")
    _wait_for_database(admin_dsn)
    _wait_for_database(development_dsn(config, "postgres", standby=True), recovery=True)
    migrator_dsn = development_dsn(config, "ctower_migrator")
    apply_migrations(migrator_dsn, role_admin_dsn=admin_dsn)
    configure_development_durability(migrator_dsn)
    _wait_for_sync(config)


def _create_database(config: DevelopmentConfig) -> None:
    _verify_local_image()
    _docker("network", "create", "--subnet", _SUBNET, _NETWORK)
    _docker("volume", "create", _PRIMARY_VOLUME)
    _docker("volume", "create", _STANDBY_VOLUME)
    start_primary(config)
    admin_dsn = development_dsn(config, "postgres")
    _wait_for_database(admin_dsn)
    _enable_replication_hba()
    provision_database_roles(admin_dsn)
    apply_migrations(
        development_dsn(config, "ctower_migrator"),
        role_admin_dsn=admin_dsn,
    )
    _set_role_passwords(config)
    _clone_standby(config)
    _start_standby(config)
    _enable_sync(config)
    configure_development_durability(development_dsn(config, "ctower_migrator"))
    _replace_hba(_PRIMARY)
    _replace_hba(_STANDBY)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute("SELECT pg_reload_conf()")
    with psycopg.connect(
        development_dsn(config, "postgres", standby=True),
        autocommit=True,
    ) as connection:
        connection.execute("SELECT pg_reload_conf()")
    _wait_for_sync(config)


def install_units(unit_root: Path) -> None:
    """Install secret-free user units and start the database/API prerequisites."""

    destination = _config_home() / "systemd" / "user"
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    (_state_home() / "ctower").mkdir(mode=0o700, parents=True, exist_ok=True)
    names = (
        "ctower-development-keyring.service",
        "ctower-development-db.service",
        "ctower-development-api.service",
        "ctower-development-worker.service",
        "ctower-development.target",
    )
    for name in names:
        source = unit_root / name
        if not source.is_file():
            raise FileNotFoundError(f"missing authored unit: {source}")
        shutil.copyfile(source, destination / name)
        (destination / name).chmod(0o644)
    _systemctl("daemon-reload")
    _systemctl(
        "enable",
        "ctower-development-keyring.service",
        "ctower-development-db.service",
        "ctower-development-api.service",
    )
    _systemctl(
        "restart",
        "ctower-development-keyring.service",
        "ctower-development-db.service",
        "ctower-development-api.service",
    )


_OPERATOR_FACING_VERBS = ("ctowerctl", "ctl", "ctower-shadow-ctl")


def expose_cli() -> dict[str, object]:
    """Link the installed operator-facing verbs onto PATH and declare this instance."""

    binary_directory = runtime_home() / "venv" / "bin"
    if not binary_directory.is_dir():
        raise RuntimeError("the persistent runtime is not installed")
    target_directory = _bin_home()
    target_directory.mkdir(parents=True, exist_ok=True)
    linked: list[Path] = []
    for name in _OPERATOR_FACING_VERBS:
        source = binary_directory / name
        if not source.is_file():
            raise RuntimeError(f"the installed runtime is missing the {name} entry point")
        destination = target_directory / name
        _atomic_symlink(source, destination)
        linked.append(destination)
    config = load_config()
    catalog_path = write_catalog(
        CliInstanceCatalog.model_validate(
            {
                "schema": "ctower.cli-instances/v1",
                "instances": (
                    {
                        "name": "development",
                        "base_url": f"http://{config.api_host}:{config.api_port}",
                    },
                ),
            }
        )
    )
    return {
        "schema": "ctower.cli-exposure/v1",
        "linked": [str(path) for path in linked],
        "catalog": str(catalog_path),
    }


def _atomic_symlink(source: Path, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(source)
    temporary.replace(destination)


def _bin_home() -> Path:
    return Path.home() / ".local" / "bin"


def keyring_unlock_main() -> None:
    """Unlock the login collection of the owner-only development account."""

    unlock_development_keyring()


def observe() -> dict[str, object]:
    """Return a secret-free exact observation of the persistent shadow instance."""

    config = load_config()
    state = load_state()
    with psycopg.connect(development_dsn(config, "postgres")) as connection:
        policy = connection.execute(
            "SELECT policy_ref, mode, standby_identity FROM durability_policy_state WHERE singleton"
        ).fetchone()
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM tenants), (SELECT count(*) FROM tickets)"
        ).fetchone()
        sync = connection.execute(
            """
            SELECT state, sync_state FROM pg_stat_replication
            WHERE application_name = 'ctower_i1_ack'
            """
        ).fetchone()
    health = PostgresRecord(
        development_dsn(config, "ctower_runtime"),
        standby_dsn=development_dsn(config, "postgres", standby=True),
    ).durability_health(now=datetime.now(UTC))
    worker_state = unit_state("ctower-development-worker.service")
    finalizer_health = observe_finalizer_health(worker_state)
    return {
        "schema": "ctower.development-observation/v1",
        "label": config.label,
        "api": unit_state("ctower-development-api.service"),
        "worker": worker_state,
        "database": unit_state("ctower-development-db.service"),
        "primary_container": _container_state(_PRIMARY),
        "standby_container": _container_state(_STANDBY),
        "policy": list(policy) if policy is not None else None,
        "replication": list(sync) if sync is not None else None,
        "durability_health": {
            "status": health.status.value,
            "reason": health.reason,
        },
        "finalizer_health": finalizer_health.model_dump(mode="json", by_alias=True),
        "tenant_id": str(state.tenant_id),
        "counts": {"tenants": counts[0], "tickets": counts[1]} if counts is not None else None,
        "installation": str(runtime_home().resolve(strict=True)),
    }


def _ensure_config_and_secrets(*, create_missing: bool) -> DevelopmentConfig:
    expected = DevelopmentConfig.model_validate(
        {
            "schema": "ctower.development-runtime/v1",
            "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
            "api_host": "127.0.0.1",
            "api_port": 8091,
            "database_host": "127.0.0.1",
            "database_name": "ctower",
            "primary_port": 55432,
            "standby_port": 55433,
            "postgres_image": _IMAGE,
            **_SECRET_REFS,
        }
    )
    if config_path().exists():
        if load_config() != expected:
            raise RuntimeError("existing development configuration differs from the fixed E2 shape")
    else:
        if not create_missing:
            raise RuntimeError("existing development database configuration is missing")
        write_config(expected)
    for reference in _SECRET_REFS.values():
        try:
            load_secret(reference)
        except SecretReferenceMissingError:
            if not create_missing:
                raise RuntimeError(
                    "existing development database secret reference is missing"
                ) from None
            put_secret(reference, secrets.token_urlsafe(48))
    return expected


def _clone_standby(config: DevelopmentConfig) -> None:
    _prepare_standby_volume()
    try:
        _run_owned_container(
            _STANDBY_CLONE,
            [
                "-i",
                "--pull",
                "never",
                "--user",
                "postgres",
                "--network",
                _NETWORK,
                "-v",
                f"{_STANDBY_VOLUME}:/var/lib/postgresql/data",
                _IMAGE,
                "pg_basebackup",
                "--dbname=host=primary user=postgres application_name=ctower_i1_ack",
                "--password",
                "--pgdata=/var/lib/postgresql/data",
                "--write-recovery-conf",
                "--wal-method=stream",
                "--create-slot",
                "--slot=ctower_development_ack",
            ],
            input_text=load_secret(config.postgres_admin_secret_ref) + "\n",
        )
    except process_execution.ProcessTimeoutError:
        _prepare_standby_volume()
        raise


def _prepare_standby_volume() -> None:
    _run_owned_container(
        _STANDBY_PREPARER,
        [
            "--pull",
            "never",
            "-v",
            f"{_STANDBY_VOLUME}:/var/lib/postgresql/data",
            _IMAGE,
            "sh",
            "-c",
            (
                "find /var/lib/postgresql/data -mindepth 1 -delete && "
                "chown postgres:postgres /var/lib/postgresql/data && "
                "chmod 700 /var/lib/postgresql/data"
            ),
        ],
    )


def _start_standby(config: DevelopmentConfig) -> None:
    _docker(
        "run",
        "-d",
        "--pull",
        "never",
        "--restart",
        "unless-stopped",
        "--name",
        _STANDBY,
        "--network",
        _NETWORK,
        "-p",
        f"127.0.0.1:{config.standby_port}:5432",
        "-v",
        f"{_STANDBY_VOLUME}:/var/lib/postgresql/data",
        _IMAGE,
        "-c",
        "hot_standby=on",
        "-c",
        "cluster_name=ctower_i1_standby",
    )
    _wait_for_database(development_dsn(config, "postgres", standby=True), recovery=True)


def _enable_replication_hba() -> None:
    _run(
        [
            docker_path(),
            "exec",
            _PRIMARY,
            "sh",
            "-c",
            (
                "printf '%s\\n' "
                "'host replication postgres 10.253.216.0/24 scram-sha-256' "
                ">> /var/lib/postgresql/data/pg_hba.conf"
            ),
        ],
        timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
    )
    config = load_config()
    with psycopg.connect(development_dsn(config, "postgres"), autocommit=True) as connection:
        connection.execute("SELECT pg_reload_conf()")


def _set_role_passwords(config: DevelopmentConfig) -> None:
    roles = {
        "postgres": config.postgres_admin_secret_ref,
        "ctower_migrator": config.migrator_secret_ref,
        "ctower_runtime": config.runtime_secret_ref,
        "ctower_projection_runtime": config.projection_secret_ref,
    }
    with psycopg.connect(development_dsn(config, "postgres"), autocommit=True) as connection:
        for role, reference in roles.items():
            connection.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal(postgres_scram_verifier(load_secret(reference))),
                )
            )


def _enable_sync(config: DevelopmentConfig) -> None:
    with psycopg.connect(development_dsn(config, "postgres"), autocommit=True) as connection:
        connection.execute("ALTER SYSTEM SET synchronous_standby_names = 'FIRST 1 (ctower_i1_ack)'")
        connection.execute("SELECT pg_reload_conf()")
    _wait_for_sync(config)


def _replace_hba(container: str) -> None:
    _run(
        [
            docker_path(),
            "exec",
            "-i",
            container,
            "sh",
            "-c",
            "cat > /var/lib/postgresql/data/pg_hba.conf",
        ],
        timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
        input_text=_HBA,
    )


def _wait_for_database(dsn: str, *, recovery: bool = False) -> None:
    deadline = time.monotonic() + 30
    last_error: psycopg.Error | None = None
    while time.monotonic() < deadline:
        try:
            if _database_ready(dsn, recovery=recovery):
                return
        except psycopg.Error as error:
            last_error = error
        time.sleep(0.1)
    raise RuntimeError("development PostgreSQL did not reach its required state") from last_error


def _database_ready(dsn: str, *, recovery: bool) -> bool:
    with psycopg.connect(dsn, connect_timeout=1) as connection:
        return not recovery or connection.execute("SELECT pg_is_in_recovery()").fetchone() == (
            True,
        )


def _wait_for_sync(config: DevelopmentConfig) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with psycopg.connect(development_dsn(config, "postgres")) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_stat_replication
                WHERE application_name = 'ctower_i1_ack'
                  AND state = 'streaming' AND sync_state = 'sync'
                """
            ).fetchone()
        if row is not None:
            return
        time.sleep(0.1)
    raise RuntimeError("development ACK standby did not become synchronous")


def _verify_local_image() -> None:
    output = _docker("image", "inspect", "--format={{json .RepoDigests}}", _IMAGE)
    digests = json.loads(output)
    if not isinstance(digests, list) or _IMAGE not in digests:
        raise RuntimeError("the exact local PostgreSQL image digest is unavailable")


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


def _unit_known(name: str) -> bool:
    result = process_execution.run(
        ["/usr/bin/systemctl", "--user", "cat", name],
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
        check=False,
        discard_output=True,
    )
    return result.returncode == 0


def _docker(*arguments: str) -> str:
    return _run(
        [docker_path(), *arguments],
        timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
        capture=True,
    )


def _run_owned_container(
    name: str,
    arguments: list[str],
    *,
    input_text: str | None = None,
) -> None:
    try:
        _run(
            [docker_path(), "run", "--rm", "--name", name, *arguments],
            timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
            input_text=input_text,
        )
    except process_execution.ProcessTimeoutError:
        _force_remove_container(name)
        raise


def _force_remove_container(name: str) -> None:
    process_execution.run(
        [docker_path(), "container", "rm", "--force", name],
        timeout_seconds=_LIFECYCLE_TIMEOUT_SECONDS,
        check=False,
        discard_output=True,
    )


def _systemctl(*arguments: str) -> None:
    _run(
        ["/usr/bin/systemctl", "--user", *arguments],
        timeout_seconds=_SYSTEMD_TIMEOUT_SECONDS,
    )


def _run(
    arguments: list[str],
    *,
    timeout_seconds: float,
    input_text: str | None = None,
    capture: bool = False,
) -> str:
    result = process_execution.run(
        arguments,
        timeout_seconds=timeout_seconds,
        check=True,
        input_text=input_text,
        capture_output=capture,
    )
    return (result.stdout or "") if capture else ""


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
