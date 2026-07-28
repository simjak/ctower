"""Security regressions at the protected development-runtime boundary."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest

import tools.development_runtime.ctl as shadow_ctl
import tools.development_runtime.interface as runtime_interface
import tools.process_execution as process_execution  # noqa: PLR0402
from ctower_api.development_config import DevelopmentConfig

__all__: tuple[str, ...] = ()

_BASE_URL_PREFIXES = tuple(f"--{'base-url'[:length]}" for length in range(1, len("base-url") + 1))
_PROBE_PROCESS_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class _ShadowConfig:
    api_host: str
    api_port: int
    operator_secret_ref: str
    commander_secret_ref: str


@dataclass(frozen=True, slots=True)
class _RuntimeSecretReferences:
    postgres_admin_secret_ref: str
    migrator_secret_ref: str = ""
    runtime_secret_ref: str = ""
    projection_secret_ref: str = ""


@dataclass(frozen=True, slots=True)
class _PasswordProbe:
    docker: str
    container: str
    bootstrap_dsn: str
    marker: str
    port: int


@dataclass(frozen=True, slots=True)
class _CloneProbe:
    docker: str
    container: str
    preparer: str
    volume: str
    wrapper: Path
    probe_id: str


@pytest.mark.parametrize("prefix", _BASE_URL_PREFIXES)
@pytest.mark.parametrize("joined", [False, True])
def test_shadow_cli_rejects_every_base_url_prefix_before_credentials_or_client(
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
    *,
    joined: bool,
) -> None:
    observed: list[str] = []
    attacker = "https://attacker.invalid"
    override = [f"{prefix}={attacker}"] if joined else [prefix, attacker]

    def config() -> _ShadowConfig:
        observed.append("config")
        return _ShadowConfig("127.0.0.1", 8091, "operator", "commander")

    def credential(_reference: str) -> str:
        observed.append("credential")
        return "credential"

    def client(_arguments: list[str], **_options: object) -> int:
        observed.append("client")
        return 0

    monkeypatch.setattr(shadow_ctl, "load_config", config)
    monkeypatch.setattr(shadow_ctl, "load_secret", credential)
    monkeypatch.setattr(shadow_ctl, "ctowerctl_main", client)
    monkeypatch.setattr(sys, "argv", ["ctower-shadow-ctl", *override, "control", "health"])

    with pytest.raises(SystemExit, match="usage: ctower-shadow-ctl"):
        shadow_ctl.main()

    assert observed == []


def test_role_password_error_never_exposes_plaintext_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _password_probe() as probe:
        with psycopg.connect(probe.bootstrap_dsn, autocommit=True) as connection:
            connection.execute("CREATE ROLE ctower_migrator LOGIN")
            connection.execute("CREATE ROLE ctower_runtime LOGIN")
        config = cast(
            DevelopmentConfig,
            _RuntimeSecretReferences("postgres", "migrator", "runtime", "projection"),
        )
        monkeypatch.setattr(
            runtime_interface,
            "development_dsn",
            lambda _config, _role: probe.bootstrap_dsn,
        )
        monkeypatch.setattr(runtime_interface, "load_secret", lambda _reference: probe.marker)

        with pytest.raises(psycopg.errors.UndefinedObject) as raised:
            runtime_interface._set_role_passwords(config)

        logs = _wait_for_probe_log(probe)
        assert probe.marker not in str(raised.value)
        assert probe.marker not in logs
        password_dsn = f"postgresql://postgres:{probe.marker}@127.0.0.1:{probe.port}/postgres"
        with psycopg.connect(password_dsn) as connection:
            assert connection.execute("SELECT current_user").fetchone() == ("postgres",)


def test_clone_timeout_removes_daemon_container_and_partial_volume(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _clone_probe(tmp_path) as probe:
        monkeypatch.setattr(runtime_interface, "_docker_path", lambda: str(probe.wrapper))
        monkeypatch.setattr(runtime_interface, "_STANDBY_CLONE", probe.container)
        monkeypatch.setattr(runtime_interface, "_STANDBY_PREPARER", probe.preparer)
        monkeypatch.setattr(runtime_interface, "_STANDBY_VOLUME", probe.volume)
        monkeypatch.setattr(runtime_interface, "_NETWORK", f"unused-{probe.probe_id}")
        monkeypatch.setattr(runtime_interface, "_LIFECYCLE_TIMEOUT_SECONDS", 1.0)
        monkeypatch.setattr(runtime_interface, "load_secret", lambda _reference: "credential")
        config = cast(DevelopmentConfig, _RuntimeSecretReferences("postgres"))

        with pytest.raises(process_execution.ProcessTimeoutError):
            runtime_interface._clone_standby(config)

        inspection = _probe_process(
            [probe.docker, "container", "inspect", probe.container],
            check=False,
            discard=True,
        )
        assert inspection.returncode != 0
        _assert_partial_clone_removed(probe)


@contextmanager
def _password_probe() -> Iterator[_PasswordProbe]:
    docker = runtime_interface._docker_path()
    probe_id = uuid4().hex
    container = f"ctower-pr60-g3-password-{probe_id}"
    bootstrap_password = f"bootstrap-{probe_id}"
    marker = f"ctower-g3-plaintext-password-{probe_id}"
    _start_password_probe(docker, container, bootstrap_password)
    try:
        port = _published_postgres_port(docker, container)
        dsn = f"postgresql://postgres:{bootstrap_password}@127.0.0.1:{port}/postgres"
        _wait_for_probe_database(dsn)
        yield _PasswordProbe(docker, container, dsn, marker, port)
    finally:
        _probe_process(
            [docker, "container", "rm", "--force", container],
            check=False,
            discard=True,
        )


def _start_password_probe(docker: str, container: str, password: str) -> None:
    _probe_process(
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            container,
            "--publish",
            "127.0.0.1::5432",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            runtime_interface._IMAGE,
            "-c",
            "log_min_error_statement=error",
            "-c",
            "log_parameter_max_length_on_error=2048",
        ]
    )


@contextmanager
def _clone_probe(tmp_path: Path) -> Iterator[_CloneProbe]:
    docker = runtime_interface._docker_path()
    probe_id = uuid4().hex
    probe = _CloneProbe(
        docker,
        f"ctower-pr60-g3-clone-{probe_id}",
        f"ctower-pr60-g3-prepare-{probe_id}",
        f"ctower-pr60-g3-volume-{probe_id}",
        tmp_path / "docker-timeout-probe",
        probe_id,
    )
    probe.wrapper.write_text(_timeout_wrapper_source(probe), encoding="utf-8")
    probe.wrapper.chmod(0o700)
    _probe_process([docker, "volume", "create", probe.volume])
    try:
        yield probe
    finally:
        for name in (probe.container, probe.preparer):
            _probe_process(
                [docker, "container", "rm", "--force", name],
                check=False,
                discard=True,
            )
        _probe_process([docker, "volume", "rm", probe.volume], check=False, discard=True)


def _timeout_wrapper_source(probe: _CloneProbe) -> str:
    return (
        "\n".join(
            (
                "#!/usr/bin/env python3",
                "import os",
                "import sys",
                f"docker = {probe.docker!r}",
                f"container = {probe.container!r}",
                f"image = {runtime_interface._IMAGE!r}",
                "arguments = sys.argv[1:]",
                "if arguments and arguments[0] == 'run' and 'pg_basebackup' in arguments:",
                "    mount = arguments[arguments.index('-v') + 1]",
                "    os.execv(docker, [",
                "        docker, 'run', '--rm', '--name', container, '-v', mount, image,",
                "        'sh', '-c',",
                "        \"touch /var/lib/postgresql/data/partial; trap '' TERM; sleep 30\",",
                "    ])",
                "os.execv(docker, [docker, *arguments])",
            )
        )
        + "\n"
    )


def _assert_partial_clone_removed(probe: _CloneProbe) -> None:
    _probe_process(
        [
            probe.docker,
            "run",
            "--rm",
            "--volume",
            f"{probe.volume}:/data",
            runtime_interface._IMAGE,
            "test",
            "!",
            "-e",
            "/data/partial",
        ]
    )


def _probe_process(
    arguments: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    discard: bool = False,
) -> subprocess.CompletedProcess[str]:
    return process_execution.run(
        arguments,
        timeout_seconds=_PROBE_PROCESS_TIMEOUT_SECONDS,
        check=check,
        capture_output=capture,
        discard_output=discard,
    )


def _published_postgres_port(docker: str, container: str) -> int:
    result = _probe_process([docker, "port", container, "5432/tcp"], capture=True)
    return int((result.stdout or "").strip().rsplit(":", maxsplit=1)[1])


def _wait_for_probe_database(dsn: str) -> None:
    deadline = time.monotonic() + _PROBE_PROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=1):
                return
        except psycopg.OperationalError:
            time.sleep(0.1)
    raise RuntimeError("pinned PostgreSQL probe did not become ready")


def _wait_for_probe_log(probe: _PasswordProbe) -> str:
    deadline = time.monotonic() + _PROBE_PROCESS_TIMEOUT_SECONDS
    expected = 'role "ctower_projection_runtime" does not exist'
    while time.monotonic() < deadline:
        result = _probe_process([probe.docker, "logs", probe.container], capture=True)
        logs = (result.stdout or "") + (result.stderr or "")
        if expected in logs:
            return logs
        time.sleep(0.1)
    raise RuntimeError("pinned PostgreSQL probe did not emit its expected error")
