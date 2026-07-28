"""Unprivileged lifecycle tooling for the approved E2 persistent shadow instance."""

from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

from ctower_api.development_config import (
    DevelopmentConfig,
    DevelopmentState,
    config_path,
    development_dsn,
    load_config,
    load_secret,
    load_state,
    put_secret,
    state_path,
    unlock_development_keyring,
    write_config,
    write_state,
)
from ctower_client import BootstrapRequest, CtowerClient
from ctower_kernel.record.postgres import (
    PostgresRecord,
    apply_migrations,
    configure_development_durability,
    provision_bootstrap,
    provision_database_roles,
    provision_principal_credential,
)
from tools.release_manifest import verify_manifest

__all__ = ["keyring_unlock_main", "main"]

_IMAGE = "postgres@sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
_NETWORK = "ctower-development-network"
_SUBNET = "10.253.216.0/24"
_PRIMARY = "ctower-development-primary"
_STANDBY = "ctower-development-ack"
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
host replication postgres 10.253.216.0/24 trust
host all all 0.0.0.0/0 scram-sha-256
host all all ::/0 scram-sha-256
"""


def main() -> None:
    """Execute one bounded local deployment lifecycle action."""

    parser = argparse.ArgumentParser(prog="ctower-private-vps")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("database-up")
    units = commands.add_parser("install-units")
    units.add_argument("--unit-root", type=Path, required=True)
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--tenant-name", default="Ctower Development")
    bootstrap.add_argument("--tenant-slug", default="ctower-development")
    release = commands.add_parser("install-release")
    release.add_argument("--wheel", type=Path, required=True)
    release.add_argument("--manifest", type=Path, required=True)
    release.add_argument("--packs", type=Path, required=True)
    release.add_argument("--python", type=Path, required=True)
    commands.add_parser("rollback")
    commands.add_parser("observe")
    arguments = parser.parse_args()
    match arguments.command:
        case "database-up":
            database_up()
        case "install-units":
            install_units(arguments.unit_root)
        case "bootstrap":
            bootstrap_instance(arguments.tenant_name, arguments.tenant_slug)
        case "install-release":
            install_release(
                arguments.wheel,
                arguments.manifest,
                arguments.packs,
                arguments.python,
            )
        case "rollback":
            rollback()
        case _:
            print(json.dumps(observe(), sort_keys=True))


def database_up() -> None:
    """Create or restart the fixed persistent PostgreSQL 17 ACK pair."""

    config = _ensure_config_and_secrets()
    primary_exists = _container_exists(_PRIMARY)
    standby_exists = _container_exists(_STANDBY)
    if primary_exists != standby_exists:
        raise RuntimeError("incomplete development database pair requires operator recovery")
    if primary_exists:
        _docker("start", _PRIMARY, _STANDBY)
        _wait_for_database(development_dsn(config, "postgres"))
        _wait_for_database(development_dsn(config, "postgres", standby=True), recovery=True)
        _wait_for_sync(config)
        return
    _verify_local_image()
    _docker("network", "create", "--subnet", _SUBNET, _NETWORK)
    _docker("volume", "create", _PRIMARY_VOLUME)
    _docker("volume", "create", _STANDBY_VOLUME)
    _start_primary(config)
    admin_dsn = development_dsn(config, "postgres")
    _wait_for_database(admin_dsn)
    _enable_replication_hba()
    provision_database_roles(admin_dsn)
    apply_migrations(
        development_dsn(config, "ctower_migrator"),
        role_admin_dsn=admin_dsn,
    )
    _set_role_passwords(config)
    _clone_standby()
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


def bootstrap_instance(tenant_name: str, tenant_slug: str) -> None:
    """Create the first tenant, bind keyring credentials, and enable the full target."""

    if state_path().exists():
        load_state()
        raise RuntimeError("development instance is already bootstrapped")
    config = load_config()
    capability = secrets.token_urlsafe(48)
    provision_bootstrap(
        development_dsn(config, "ctower_migrator"),
        capability_input=io.StringIO(capability + "\n"),
        allowed_origin=config.api_host,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with CtowerClient(f"http://{config.api_host}:{config.api_port}") as client:
        receipt = client.bootstrap_first_tenant(
            BootstrapRequest(
                commander_name="Development Commander",
                commander_vault_ref="vault-ref:ctower/development/commander",
                operator_credential_ref="credential-ref:ctower/development/operator",
                operator_name="Development Operator",
                operator_vault_ref="vault-ref:ctower/development/operator",
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
            ),
            command_id=uuid4(),
            capability=capability,
        )
    provision_principal_credential(
        development_dsn(config, "ctower_migrator"),
        receipt.tenant_id,
        receipt.operator_id,
        credential_input=io.StringIO(load_secret(config.operator_secret_ref) + "\n"),
    )
    provision_principal_credential(
        development_dsn(config, "ctower_migrator"),
        receipt.tenant_id,
        receipt.commander_id,
        credential_input=io.StringIO(load_secret(config.commander_secret_ref) + "\n"),
    )
    write_state(
        DevelopmentState.model_validate(
            {
                "schema": "ctower.development-state/v1",
                "tenant_id": receipt.tenant_id,
                "operator_id": receipt.operator_id,
                "commander_id": receipt.commander_id,
            }
        )
    )
    _systemctl(
        "enable",
        "ctower-development-worker.service",
        "ctower-development.target",
    )
    _systemctl("restart", "ctower-development-worker.service")
    _systemctl("start", "ctower-development.target")


def install_release(wheel: Path, manifest_path: Path, packs: Path, python: Path) -> None:
    """Verify, install, and atomically select one unprivileged release."""

    manifest = verify_manifest(
        manifest_path,
        wheel,
        packs,
        python_executable=python,
    )
    release_id = f"{manifest.source_commit[:12]}-{manifest.wheel.sha256[7:19]}"
    home = _release_home()
    release = home / "releases" / release_id
    if release.exists():
        raise FileExistsError(f"release already exists: {release_id}")
    release.mkdir(mode=0o700, parents=True)
    shutil.copy2(wheel, release / wheel.name)
    shutil.copy2(manifest_path, release / "manifest.json")
    shutil.copytree(packs, release / "packs")
    _run([str(python.resolve(strict=True)), "-m", "venv", str(release / "venv")])
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to install the verified development artifact")
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(release / "venv/bin/python"),
            str(release / wheel.name),
        ]
    )
    freeze = _run(
        [
            str(release / "venv/bin/python"),
            "-m",
            "pip",
            "freeze",
            "--all",
        ],
        capture=True,
    )
    (release / "installed-distributions.txt").write_text(freeze, encoding="utf-8")
    current = home / "current"
    previous = home / "previous"
    if current.is_symlink():
        _replace_symlink(previous, current.resolve(strict=True))
    _replace_symlink(current, release)
    if _unit_known("ctower-development-api.service"):
        _systemctl(
            "restart",
            "ctower-development-api.service",
            "ctower-development-worker.service",
        )


def rollback() -> None:
    """Atomically select the verified predecessor and restart same-artifact services."""

    home = _release_home()
    current = home / "current"
    previous = home / "previous"
    if not current.is_symlink() or not previous.is_symlink():
        raise RuntimeError("rollback requires both current and previous verified releases")
    old_current = current.resolve(strict=True)
    old_previous = previous.resolve(strict=True)
    _replace_symlink(current, old_previous)
    _replace_symlink(previous, old_current)
    _systemctl(
        "restart",
        "ctower-development-api.service",
        "ctower-development-worker.service",
    )


def keyring_unlock_main() -> None:
    """Unlock only the fixed owner-only development Secret Service collection."""

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
    return {
        "schema": "ctower.development-observation/v1",
        "label": config.label,
        "api": _systemctl_state("ctower-development-api.service"),
        "worker": _systemctl_state("ctower-development-worker.service"),
        "database": _systemctl_state("ctower-development-db.service"),
        "primary_container": _container_state(_PRIMARY),
        "standby_container": _container_state(_STANDBY),
        "policy": list(policy) if policy is not None else None,
        "replication": list(sync) if sync is not None else None,
        "durability_health": {
            "status": health.status.value,
            "reason": health.reason,
        },
        "tenant_id": str(state.tenant_id),
        "counts": {"tenants": counts[0], "tickets": counts[1]} if counts is not None else None,
        "release": str((_release_home() / "current").resolve(strict=True)),
    }


def _ensure_config_and_secrets() -> DevelopmentConfig:
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
        write_config(expected)
    for reference in _SECRET_REFS.values():
        try:
            load_secret(reference)
        except RuntimeError:
            put_secret(reference, secrets.token_urlsafe(48))
    return expected


def _start_primary(config: DevelopmentConfig) -> None:
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
        "-e",
        "POSTGRES_DB=ctower",
        "-e",
        "POSTGRES_HOST_AUTH_METHOD=trust",
        "-e",
        "POSTGRES_USER=postgres",
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


def _clone_standby() -> None:
    _docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "-v",
        f"{_STANDBY_VOLUME}:/var/lib/postgresql/data",
        _IMAGE,
        "sh",
        "-c",
        "chown postgres:postgres /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data",
    )
    _docker(
        "run",
        "--rm",
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
        "--pgdata=/var/lib/postgresql/data",
        "--write-recovery-conf",
        "--wal-method=stream",
        "--create-slot",
        "--slot=ctower_development_ack",
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
            _docker_path(),
            "exec",
            _PRIMARY,
            "sh",
            "-c",
            (
                "printf '%s\\n' 'host replication postgres 10.253.216.0/24 trust' "
                ">> /var/lib/postgresql/data/pg_hba.conf"
            ),
        ]
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
                    sql.Literal(load_secret(reference)),
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
            _docker_path(),
            "exec",
            "-i",
            container,
            "sh",
            "-c",
            "cat > /var/lib/postgresql/data/pg_hba.conf",
        ],
        input_text=_HBA,
    )


def _wait_for_database(dsn: str, *, recovery: bool = False) -> None:
    deadline = time.monotonic() + 30
    last_error: psycopg.Error | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1) as connection:
                if not recovery or connection.execute("SELECT pg_is_in_recovery()").fetchone() == (
                    True,
                ):
                    return
        except psycopg.Error as error:
            last_error = error
        time.sleep(0.1)
    raise RuntimeError("development PostgreSQL did not reach its required state") from last_error


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
    result = subprocess.run(  # noqa: S603 - executable and inspect arguments are closed constants
        [_docker_path(), "container", "inspect", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _container_state(name: str) -> str:
    return _docker("inspect", "--format={{.State.Status}}", name).strip()


def _unit_known(name: str) -> bool:
    result = subprocess.run(  # noqa: S603 - exact user-unit query
        ["/usr/bin/systemctl", "--user", "cat", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _systemctl_state(name: str) -> str:
    result = subprocess.run(  # noqa: S603 - exact user-unit observation
        ["/usr/bin/systemctl", "--user", "is-active", name],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _docker(*arguments: str) -> str:
    return _run([_docker_path(), *arguments], capture=True)


def _docker_path() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is required for the persistent development database")
    return str(Path(docker).resolve(strict=True))


def _systemctl(*arguments: str) -> None:
    _run(["/usr/bin/systemctl", "--user", *arguments])


def _run(
    arguments: list[str],
    *,
    input_text: str | None = None,
    capture: bool = False,
) -> str:
    result = subprocess.run(  # noqa: S603 - callers construct bounded lifecycle commands
        arguments,
        check=True,
        input=input_text,
        capture_output=capture,
        text=True,
    )
    return result.stdout if capture else ""


def _replace_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = link.with_name(link.name + ".next")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"stale release pointer requires operator review: {temporary}")
    temporary.symlink_to(target)
    temporary.replace(link)


def _release_home() -> Path:
    return _data_home() / "ctower-development"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))


def _state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
