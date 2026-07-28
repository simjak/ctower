"""Direct operation and protected-wrapper tests for the E2 development runtime."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, Self, TextIO
from uuid import UUID, uuid4

import psycopg
import pytest

import ctower_kernel.record.postgres as record_postgres
import tools.development_runtime.bootstrap as bootstrap_module
import tools.development_runtime.ctl as ctl_module
import tools.development_runtime.installation as installation_module
import tools.development_runtime.interface as lifecycle
import tools.development_runtime.primary as primary_module
import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import (
    DevelopmentConfig,
    bootstrap_checkpoint_path,
    load_bootstrap_checkpoint,
    load_state,
)
from ctower_api.development_secrets import SecretReferenceMissingError
from ctower_kernel.record import DurabilityFinalizationBatch

__all__: tuple[str, ...] = ()
EXPECTED_REPLAY_ATTEMPTS = 2


def _config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate(
        {
            "schema": "ctower.development-runtime/v1",
            "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
            "api_host": "127.0.0.1",
            "api_port": 8091,
            "database_host": "127.0.0.1",
            "database_name": "ctower",
            "primary_port": 55432,
            "standby_port": 55433,
            "postgres_image": lifecycle._IMAGE,
            **lifecycle._SECRET_REFS,
        }
    )


def _observe_runtime_run(
    calls: list[tuple[list[str], str | None]],
    arguments: list[str],
    *,
    timeout_seconds: float,
    input_text: str | None = None,
    capture: bool = False,
) -> str:
    del capture, timeout_seconds
    calls.append((arguments, input_text))
    return ""


def _observe_docker(calls: list[tuple[str, ...]], *arguments: str) -> str:
    calls.append(arguments)
    return ""


@pytest.mark.parametrize("override", ["--base-url", "--base-url=https://override.invalid"])
def test_shadow_ctl_refuses_every_base_url_override(
    monkeypatch: pytest.MonkeyPatch, override: str
) -> None:
    monkeypatch.setattr(sys, "argv", ["ctower-shadow-ctl", "ticket", "list", override])
    monkeypatch.setattr(
        ctl_module,
        "load_config",
        lambda: (_ for _ in ()).throw(AssertionError("config must not be loaded")),
    )

    with pytest.raises(SystemExit, match="usage"):
        ctl_module.main()


def test_locked_keyring_never_mints_replacement_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    minted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        lifecycle,
        "load_secret",
        lambda _reference: (_ for _ in ()).throw(RuntimeError("keyring locked")),
    )
    monkeypatch.setattr(lifecycle, "put_secret", lambda key, value: minted.append((key, value)))

    with pytest.raises(RuntimeError, match="keyring locked"):
        lifecycle._ensure_config_and_secrets(create_missing=True)

    assert minted == []


def test_existing_database_pair_reapplies_migrations_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    observed: list[object] = []

    def ensure(*, create_missing: bool) -> DevelopmentConfig:
        observed.append(("secrets", create_missing))
        return config

    def docker(*args: str) -> str:
        observed.append(("docker", args))
        return ""

    monkeypatch.setattr(lifecycle, "_container_exists", lambda _name: True)
    monkeypatch.setattr(lifecycle, "_ensure_config_and_secrets", ensure)
    monkeypatch.setattr(lifecycle, "_docker", docker)
    monkeypatch.setattr(
        lifecycle,
        "development_dsn",
        lambda _config, role, *, standby=False: f"{role}:{standby}",
    )
    monkeypatch.setattr(
        lifecycle,
        "_wait_for_database",
        lambda dsn, *, recovery=False: observed.append(("wait", dsn, recovery)),
    )
    monkeypatch.setattr(
        lifecycle,
        "apply_migrations",
        lambda dsn, *, role_admin_dsn: observed.append(("migrate", dsn, role_admin_dsn)),
    )
    monkeypatch.setattr(
        lifecycle,
        "configure_development_durability",
        lambda dsn: observed.append(("policy", dsn)),
    )
    monkeypatch.setattr(lifecycle, "_wait_for_sync", lambda _config: observed.append(("sync",)))

    lifecycle.database_up()

    assert ("secrets", False) in observed
    assert ("migrate", "ctower_migrator:False", "postgres:False") in observed
    assert ("policy", "ctower_migrator:False") in observed
    assert observed[-1] == ("sync",)


def test_primary_and_clone_use_stdin_secret_without_trust_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    credential_value = "v" * 48
    run_calls: list[tuple[list[str], str | None]] = []
    docker_calls: list[tuple[str, ...]] = []
    attachments: list[tuple[str, str]] = []
    readiness = iter((False, True))

    monkeypatch.setattr(primary_module, "_docker_path", lambda: "/usr/bin/docker")
    monkeypatch.setattr(primary_module, "load_secret", lambda _reference: credential_value)
    monkeypatch.setattr(lifecycle, "load_secret", lambda _reference: credential_value)
    monkeypatch.setattr(primary_module, "_container_exists", lambda _name: False)
    monkeypatch.setattr(primary_module, "_container_state", lambda _name: "created")
    monkeypatch.setattr(primary_module, "_container_database_ready", lambda: next(readiness))
    monkeypatch.setattr(lifecycle, "_run", partial(_observe_runtime_run, run_calls))
    monkeypatch.setattr(
        primary_module,
        "_docker",
        partial(_observe_docker, docker_calls),
    )
    monkeypatch.setattr(
        primary_module,
        "_attach_container_input",
        lambda value: attachments.append((primary_module._INITIALIZER, value)),
    )

    primary_module.start_primary(config)
    lifecycle._clone_standby(config)

    rendered = tuple(" ".join(arguments) for arguments in docker_calls) + tuple(
        " ".join(arguments) for arguments, _input in run_calls
    )
    assert all(credential_value not in command for command in rendered)
    assert all("POSTGRES_HOST_AUTH_METHOD=trust" not in command for command in rendered)
    assert "POSTGRES_PASSWORD_FILE=/dev/stdin" in rendered[0]
    assert any("pg_basebackup" in command and "--password" in command for command in rendered)
    assert attachments == [(primary_module._INITIALIZER, credential_value)]
    assert run_calls[-1][1] == credential_value + "\n"


def test_finalizer_cursor_rotates_past_a_refusing_head_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = (datetime.now(UTC), uuid4(), uuid4())
    observed: list[object] = []
    results = iter(
        (
            (DurabilityFinalizationBatch(1, 0, 0, 1), cursor),
            (DurabilityFinalizationBatch(1, 1, 0, 0), None),
        )
    )

    def finalize(
        _primary: str,
        _standby: str | None,
        *,
        limit: int,
        after: object,
        telemetry: object,
    ) -> tuple[DurabilityFinalizationBatch, object]:
        observed.append((limit, after, telemetry))
        return next(results)

    monkeypatch.setattr(record_postgres, "_finalize_pending", finalize)
    finalizer = record_postgres.PostgresDurabilityFinalizer("primary", standby_dsn="standby")

    assert finalizer.finalize_pending(limit=1).refused == 1
    assert finalizer.finalize_pending(limit=1).accepted == 1
    assert observed == [(1, None, None), (1, cursor, None)]


def test_initialization_attach_requires_a_still_running_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(primary_module, "_docker_path", lambda: "/usr/bin/docker")
    monkeypatch.setattr(
        process_execution,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            process_execution.ProcessTimeoutError(["docker", "attach"], 1)
        ),
    )
    primary_module._attach_container_input("value")
    monkeypatch.setattr(
        process_execution,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    with pytest.raises(RuntimeError, match="exited"):
        primary_module._attach_container_input("value")


class _BootstrapClient:
    attempts: ClassVar[list[tuple[UUID, str]]] = []
    fail_first = True

    def __init__(self, _base_url: str) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def bootstrap_first_tenant(
        self, _request: object, *, command_id: UUID, capability: str
    ) -> object:
        self.attempts.append((command_id, capability))
        if self.fail_first:
            type(self).fail_first = False
            raise RuntimeError("simulated client interruption")
        return SimpleNamespace(tenant_id=uuid4(), operator_id=uuid4(), commander_id=uuid4())


class _ObservationConnection:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def execute(self, statement: str) -> object:
        if "durability_policy_state" in statement:
            row: tuple[object, ...] | None = ("policy", "development_offhost_ack", "standby")
        elif "count(*)" in statement:
            row = (1, 2)
        else:
            row = ("streaming", "sync")
        return SimpleNamespace(fetchone=lambda: row)


def test_observe_exposes_finalizer_liveness_as_a_separate_typed_dimension(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config()
    tenant_id = uuid4()
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    health = SimpleNamespace(status=SimpleNamespace(value="DEGRADED"), reason="cp3d")
    finalizer = {
        "schema": "ctower.development-finalizer-health/v1",
        "status": "HEALTHY",
        "reason": "progress_observed",
    }
    monkeypatch.setattr(lifecycle, "load_config", lambda: config)
    monkeypatch.setattr(lifecycle, "load_state", lambda: SimpleNamespace(tenant_id=tenant_id))
    monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: _ObservationConnection())
    monkeypatch.setattr(lifecycle, "development_dsn", lambda *_args, **_kwargs: "dsn")
    monkeypatch.setattr(
        lifecycle,
        "PostgresRecord",
        lambda *_args, **_kwargs: SimpleNamespace(durability_health=lambda **_values: health),
    )
    monkeypatch.setattr(lifecycle, "_systemctl_state", lambda _name: "active")
    monkeypatch.setattr(lifecycle, "_container_state", lambda _name: "running")
    monkeypatch.setattr(lifecycle, "runtime_home", lambda: runtime_home)
    monkeypatch.setattr(
        lifecycle,
        "observe_finalizer_health",
        lambda _state: SimpleNamespace(model_dump=lambda **_options: finalizer),
    )

    observation = lifecycle.observe()

    assert observation["durability_health"] == {"status": "DEGRADED", "reason": "cp3d"}
    assert observation["finalizer_health"] == finalizer
    assert observation["installation"] == str(runtime_home)


def test_bootstrap_retry_reuses_checkpoint_and_finishes_after_interruption(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    config = _config()
    secrets_by_reference = {
        config.operator_secret_ref: "o" * 48,
        config.commander_secret_ref: "c" * 48,
    }
    provisioned: list[tuple[str, datetime]] = []
    systemctl: list[tuple[str, ...]] = []
    _BootstrapClient.attempts = []
    _BootstrapClient.fail_first = True

    _patch_bootstrap_storage(monkeypatch, config, secrets_by_reference)
    _patch_bootstrap_services(monkeypatch, provisioned, systemctl)

    with pytest.raises(RuntimeError, match="simulated client interruption"):
        bootstrap_module.bootstrap_instance("Tenant", "tenant-one")
    checkpoint = load_bootstrap_checkpoint()
    assert bootstrap_checkpoint_path().exists()

    bootstrap_module.bootstrap_instance("Tenant", "tenant-one")

    assert len(_BootstrapClient.attempts) == EXPECTED_REPLAY_ATTEMPTS
    assert _BootstrapClient.attempts[0] == _BootstrapClient.attempts[1]
    assert _BootstrapClient.attempts[0][0] == checkpoint.command_id
    assert provisioned[0][0] == provisioned[1][0]
    assert load_state().tenant_id is not None
    assert not bootstrap_checkpoint_path().exists()
    assert systemctl[-1] == ("start", "ctower-development.target")


def _patch_bootstrap_storage(
    monkeypatch: pytest.MonkeyPatch,
    config: DevelopmentConfig,
    secrets_by_reference: dict[str, str],
) -> None:
    def store_value(reference: str, value: str) -> None:
        secrets_by_reference[reference] = value

    monkeypatch.setattr(bootstrap_module, "load_config", lambda: config)
    monkeypatch.setattr(
        bootstrap_module,
        "development_dsn",
        lambda _config, _role, *, standby=False: f"dsn:{standby}",
    )
    monkeypatch.setattr(bootstrap_module, "put_secret", store_value)
    monkeypatch.setattr(bootstrap_module, "load_secret", secrets_by_reference.__getitem__)
    monkeypatch.setattr(
        bootstrap_module,
        "delete_secret",
        lambda reference: secrets_by_reference.pop(reference, None),
    )


def _patch_bootstrap_services(
    monkeypatch: pytest.MonkeyPatch,
    provisioned: list[tuple[str, datetime]],
    systemctl: list[tuple[str, ...]],
) -> None:
    def observe_provision(
        _dsn: str,
        *,
        capability_input: TextIO,
        allowed_origin: str,
        expires_at: datetime,
    ) -> None:
        del allowed_origin
        provisioned.append((capability_input.readline().strip(), expires_at))

    monkeypatch.setattr(bootstrap_module, "provision_bootstrap", observe_provision)
    monkeypatch.setattr(
        bootstrap_module, "provision_principal_credential", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(bootstrap_module, "CtowerClient", _BootstrapClient)
    monkeypatch.setattr(bootstrap_module, "_systemctl", lambda *args: systemctl.append(args))


def test_runtime_install_executes_entrypoint_at_its_permanent_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    python = tmp_path / "python"
    python.write_text(
        """#!/bin/sh
set -eu
test "$1" = "-m"
test "$2" = "venv"
mkdir -p "$3/bin"
ln -s /bin/sh "$3/bin/python"
""",
        encoding="utf-8",
    )
    python.chmod(0o700)
    uv = tmp_path / "uv"
    uv.write_text(
        """#!/bin/sh
set -eu
python_path=
previous=
for argument in "$@"; do
    if test "$previous" = "--python"; then python_path="$argument"; fi
    previous="$argument"
done
case "$2" in
    install)
        entrypoint="$(dirname "$python_path")/ctower-private-vps"
        printf '#!%s\\n' "$python_path" > "$entrypoint"
        printf 'test "$1" = "--help"\\n' >> "$entrypoint"
        printf 'printf executed > "$(dirname "$0")/entrypoint-executed"\\n' >> "$entrypoint"
        chmod 700 "$entrypoint"
        ;;
    check) ;;
    freeze) printf 'ctower-workspace==0.0.0\\n' ;;
esac
""",
        encoding="utf-8",
    )
    uv.chmod(0o700)
    wheel = tmp_path / "artifact.whl"
    manifest = tmp_path / "manifest.json"
    packs = tmp_path / "packs"
    wheel.write_bytes(b"wheel")
    manifest.write_text("{}\n", encoding="utf-8")
    packs.mkdir()
    (packs / "pack.yaml").write_text("pack: test\n", encoding="utf-8")
    runtime = tmp_path / "data/ctower-development/runtime"
    monkeypatch.setattr(installation_module, "_data_home", lambda: tmp_path / "data")
    monkeypatch.setattr(installation_module, "verify_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(installation_module, "_uv_path", lambda: str(uv))

    installation_module.install_runtime(wheel, manifest, packs, python, tmp_path)

    entrypoint = runtime / "venv/bin/ctower-private-vps"
    assert entrypoint.read_text(encoding="utf-8").splitlines()[0] == (
        f"#!{runtime}/venv/bin/python"
    )
    assert (runtime / "installed-distributions.txt").read_text(encoding="utf-8") == (
        "ctower-workspace==0.0.0\n"
    )
    assert (runtime / "venv/bin/entrypoint-executed").read_text(encoding="utf-8") == "executed"
    assert not any("staging" in part for part in entrypoint.parts)


def test_refusing_runtime_entrypoint_fails_install_and_removes_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    python = tmp_path / "python"
    python.write_text(
        """#!/bin/sh
set -eu
test "$1" = "-m"
test "$2" = "venv"
mkdir -p "$3/bin"
ln -s /bin/sh "$3/bin/python"
""",
        encoding="utf-8",
    )
    python.chmod(0o700)
    uv = tmp_path / "uv"
    uv.write_text(
        """#!/bin/sh
set -eu
python_path=
previous=
for argument in "$@"; do
    if test "$previous" = "--python"; then python_path="$argument"; fi
    previous="$argument"
done
case "$2" in
    install)
        entrypoint="$(dirname "$python_path")/ctower-private-vps"
        printf '#!%s\\nexit 23\\n' "$python_path" > "$entrypoint"
        chmod 700 "$entrypoint"
        ;;
    check) ;;
    freeze) printf 'ctower-workspace==0.0.0\\n' ;;
esac
""",
        encoding="utf-8",
    )
    uv.chmod(0o700)
    wheel = tmp_path / "artifact.whl"
    manifest = tmp_path / "manifest.json"
    packs = tmp_path / "packs"
    wheel.write_bytes(b"wheel")
    manifest.write_text("{}\n", encoding="utf-8")
    packs.mkdir()
    (packs / "pack.yaml").write_text("pack: test\n", encoding="utf-8")
    monkeypatch.setattr(installation_module, "_data_home", lambda: tmp_path / "data")
    monkeypatch.setattr(installation_module, "verify_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(installation_module, "_uv_path", lambda: str(uv))

    with pytest.raises(subprocess.CalledProcessError):
        installation_module.install_runtime(wheel, manifest, packs, python, tmp_path)

    assert not installation_module.runtime_home().exists()


def test_failed_runtime_install_leaves_no_partial_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wheel = tmp_path / "artifact.whl"
    manifest = tmp_path / "manifest.json"
    packs = tmp_path / "packs"
    python = tmp_path / "python"
    wheel.write_bytes(b"wheel")
    manifest.write_text("{}\n", encoding="utf-8")
    packs.mkdir()
    (packs / "pack.yaml").write_text("pack: test\n", encoding="utf-8")
    python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    python.chmod(0o700)
    monkeypatch.setattr(installation_module, "_data_home", lambda: tmp_path / "data")
    monkeypatch.setattr(
        installation_module,
        "verify_manifest",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(subprocess.CalledProcessError):
        installation_module.install_runtime(wheel, manifest, packs, python, tmp_path)

    assert not installation_module.runtime_home().exists()


def test_database_unit_retries_without_fake_user_docker_dependency() -> None:
    unit = (
        Path(__file__).parents[2]
        / "deploy/private-vps/development/systemd/ctower-development-db.service"
    ).read_text(encoding="utf-8")

    assert "After=docker.service" not in unit
    assert "ExecStartPre=/usr/bin/docker info" in unit
    assert "Restart=on-failure" in unit
    assert "StartLimitIntervalSec=0" in unit


def test_service_units_select_only_the_fixed_runtime_installation() -> None:
    unit_root = Path(__file__).parents[2] / "deploy/private-vps/development/systemd"
    for name in (
        "ctower-development-keyring.service",
        "ctower-development-api.service",
        "ctower-development-worker.service",
    ):
        unit = (unit_root / name).read_text(encoding="utf-8")
        assert ".local/share/ctower-development/runtime/venv/bin/" in unit
        assert ".local/share/ctower-development/current/" not in unit


def test_missing_existing_secret_has_a_distinct_typed_failure() -> None:
    assert issubclass(SecretReferenceMissingError, RuntimeError)
