"""Build and exercise the protected CLI from one isolated installed wheel."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import venv
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from email import message_from_bytes
from pathlib import Path
from threading import Thread
from typing import cast
from uuid import uuid4

import pytest

from ._installed_bootstrap import run_installed_bootstrap_smoke

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[2]
EXIT_LOCAL_FAILURE = 74
EXIT_TEMPORARY = 75
_AUTHORITY = "packaging-fixture-authority"


@dataclass(frozen=True, slots=True)
class _InstalledWheel:
    wheel: Path
    binary_directory: Path
    environment: Mapping[str, str]
    outside_checkout: Path


@pytest.fixture(scope="module")
def installed_wheel(tmp_path_factory: pytest.TempPathFactory) -> _InstalledWheel:
    workspace = tmp_path_factory.mktemp("installed-wheel")
    wheel = _build_wheel(workspace)
    binary_directory = _install_wheel(workspace, wheel)
    outside = workspace / "outside-checkout"
    outside.mkdir()
    environment = _installed_environment(workspace, binary_directory)
    return _InstalledWheel(wheel, binary_directory, environment, outside)


def test_wheel_has_explicit_packages_resources_dependencies_and_scripts(
    installed_wheel: _InstalledWheel,
) -> None:
    with zipfile.ZipFile(installed_wheel.wheel) as archive:
        names = frozenset(archive.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_name = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        metadata = message_from_bytes(archive.read(metadata_name))
        entry_points = archive.read(entry_name).decode("utf-8")
        migration_manifest = json.loads(archive.read("ctower_kernel/migrations/manifest.json"))

    required_roots = (
        "ctower_api/",
        "ctower_client/",
        "ctower_kernel/",
        "ctowerctl/",
        "tools/",
    )
    assert all(any(name.startswith(root) for name in names) for root in required_roots)
    assert "ctower_contracts/schemas.json" in names
    declared_migrations = {
        f"ctower_kernel/migrations/{entry['path']}" for entry in migration_manifest["migrations"]
    }
    packaged_migrations = {
        name
        for name in names
        if name.startswith("ctower_kernel/migrations/") and name.endswith(".sql")
    }
    assert packaged_migrations == declared_migrations
    assert not any(
        name.startswith(("tests/", "apps/", "packages/", "generated/")) for name in names
    )
    forbidden_residue = (
        "/.coverage",
        "/.env",
        "/.git",
        "/.mypy_cache",
        "/.pytest_cache",
        "/.ruff_cache",
        "/__pycache__",
    )
    assert not any(any(residue in f"/{name}" for residue in forbidden_residue) for name in names)
    requirements = tuple(metadata.get_all("Requires-Dist", ()))
    for dependency in ("cryptography", "keyring", "platformdirs", "SecretStorage"):
        assert any(requirement.startswith(dependency) for requirement in requirements)
    assert "ctl = ctowerctl:main" in entry_points
    assert "ctowerctl = ctowerctl:main" in entry_points
    assert "ctower-development-api = ctower_api.development_runtime:api_main" in entry_points
    assert "ctower-development-keyring-unlock = tools.development_runtime:keyring_unlock_main" in (
        entry_points
    )
    assert "ctower-development-worker = ctower_api.development_runtime:worker_main" in entry_points
    assert "ctower-private-vps = tools.development_runtime:main" in entry_points
    assert "ctower-runtime-manifest = tools.runtime_manifest.__main__:main" in entry_points
    assert "ctower-shadow-ctl = tools.development_runtime.ctl:main" in entry_points


def test_installed_alias_help_and_generated_resource_are_checkout_independent(
    installed_wheel: _InstalledWheel,
) -> None:
    ctowerctl = installed_wheel.binary_directory / "ctowerctl"
    ctl = installed_wheel.binary_directory / "ctl"
    private_vps = installed_wheel.binary_directory / "ctower-private-vps"
    primary = _run((ctowerctl, "--help"), installed_wheel)
    alias = _run((ctl, "--help"), installed_wheel)
    installed_runtime_entrypoint = _run((private_vps, "--help"), installed_wheel)
    resource = _run(
        (
            installed_wheel.binary_directory / "python",
            "-I",
            "-c",
            "from pathlib import Path; import ctowerctl; "
            "from ctower_contracts import schema_for; "
            "assert schema_for('ctower.company-bundle/v1') is not None; "
            "print(Path(ctowerctl.__file__).resolve())",
        ),
        installed_wheel,
    )

    assert primary.returncode == alias.returncode == 0
    assert installed_runtime_entrypoint.returncode == 0
    assert primary.stdout == alias.stdout
    installed_path = Path(resource.stdout.strip())
    assert installed_path.is_relative_to(installed_wheel.binary_directory.parent)
    assert not installed_path.is_relative_to(ROOT)


def test_installed_bootstrap_api_control_worker_and_cli_use_packaged_migrations(
    installed_wheel: _InstalledWheel,
) -> None:
    result = run_installed_bootstrap_smoke(
        binary_directory=installed_wheel.binary_directory,
        environment=installed_wheel.environment,
        outside_checkout=installed_wheel.outside_checkout,
    )

    bootstrap = cast(dict[str, object], result["bootstrap"])
    worker = cast(dict[str, object], result["worker"])
    assert result["bootstrap_status"] == EXIT_TEMPORARY
    assert bootstrap["durability_state"] == "durability_pending"
    assert worker["tenant_count"] == 1
    kernel_path = Path(cast(str, worker["kernel_path"]))
    assert kernel_path.is_relative_to(installed_wheel.binary_directory.parent)
    assert not kernel_path.is_relative_to(ROOT)


def test_installed_read_continues_without_keyring(
    installed_wheel: _InstalledWheel,
) -> None:
    with _health_server() as (base_url, requests):
        result = _run(
            (
                installed_wheel.binary_directory / "ctl",
                "--base-url",
                base_url,
                "control",
                "health",
            ),
            installed_wheel,
            environment=_without_session_bus(installed_wheel.environment),
            stdin=f"{_AUTHORITY}\n",
        )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "HEALTHY"
    assert len(requests) == 1 and b"GET /health " in requests[0]
    assert _AUTHORITY.encode() in requests[0]


def test_installed_mutation_queues_then_missing_keyring_fails_without_state_change(
    installed_wheel: _InstalledWheel,
) -> None:
    base_url = _unused_base_url()
    first_command = uuid4()
    queued = _run(
        _ticket_create_command(installed_wheel, base_url, first_command),
        installed_wheel,
        stdin=f"{_AUTHORITY}\n",
    )
    before = _snapshot(Path(installed_wheel.environment["XDG_STATE_HOME"]))
    blocked = _run(
        _ticket_create_command(installed_wheel, base_url, uuid4()),
        installed_wheel,
        environment=_without_session_bus(installed_wheel.environment),
        stdin=f"{_AUTHORITY}\n",
    )
    status = _run(
        (
            installed_wheel.binary_directory / "ctl",
            "--base-url",
            base_url,
            "spool",
            "status",
        ),
        installed_wheel,
    )

    assert queued.returncode == EXIT_TEMPORARY
    assert json.loads(queued.stdout)["command_id"] == str(first_command)
    assert json.loads(queued.stdout)["state"] == "queued"
    assert blocked.returncode == EXIT_LOCAL_FAILURE
    assert json.loads(blocked.stdout)["state"] == "local_failure"
    assert _snapshot(Path(installed_wheel.environment["XDG_STATE_HOME"])) == before
    assert status.returncode == 0
    assert json.loads(status.stdout)["pending_count"] == 1


def _build_wheel(workspace: Path) -> Path:
    source = workspace / "source"
    source.mkdir()
    for relative in ("LICENSE", "pyproject.toml", "tools/__init__.py"):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for relative in (
        "apps/ctower-api/src",
        "apps/ctowerctl/src",
        "generated/python",
        "packages/ctower-kernel/migrations",
        "packages/ctower-kernel/src",
        "tools/development_runtime",
        "tools/runtime_manifest",
    ):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / relative, destination)
    output = workspace / "wheel"
    output.mkdir()
    _checked(
        (sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", output),
        cwd=source,
        environment=_base_environment(),
        timeout=180,
    )
    wheels = tuple(output.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _install_wheel(workspace: Path, wheel: Path) -> Path:
    environment_root = workspace / "environment"
    venv.EnvBuilder(with_pip=True).create(environment_root)
    binary_directory = environment_root / "bin"
    python = binary_directory / "python"
    outside = workspace / "installer-cwd"
    outside.mkdir()
    _checked(
        (
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--require-hashes",
            "-r",
            ROOT / "requirements/verify.txt",
        ),
        cwd=outside,
        environment=_base_environment(),
        timeout=600,
    )
    _checked(
        (python, "-m", "pip", "install", "--no-deps", wheel),
        cwd=outside,
        environment=_base_environment(),
        timeout=120,
    )
    _checked(
        (python, "-m", "pip", "check"),
        cwd=outside,
        environment=_base_environment(),
        timeout=120,
    )
    return binary_directory


def _checked(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int,
) -> None:
    process_environment = dict(environment)
    process_environment["CTOWER_TEST_COMMAND"] = json.dumps(
        tuple(str(argument) for argument in command)
    )
    result = subprocess.run(
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
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _run(
    command: Sequence[str | Path],
    installed: _InstalledWheel,
    *,
    environment: Mapping[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    process_environment = dict(environment or installed.environment)
    process_environment["CTOWER_TEST_COMMAND"] = json.dumps(
        tuple(str(argument) for argument in command)
    )
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_TEST_COMMAND')); "
            "os.execv(command[0], command)",
        ),
        cwd=installed.outside_checkout,
        env=process_environment,
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _base_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _installed_environment(workspace: Path, binary_directory: Path) -> dict[str, str]:
    environment = _base_environment()
    environment["PATH"] = f"{binary_directory}{os.pathsep}{environment['PATH']}"
    state = workspace / "state"
    state.mkdir()
    environment["XDG_STATE_HOME"] = str(state)
    return environment


def _without_session_bus(environment: Mapping[str, str]) -> dict[str, str]:
    isolated = dict(environment)
    for name in ("DBUS_SESSION_BUS_ADDRESS", "GNOME_KEYRING_CONTROL"):
        isolated.pop(name, None)
    return isolated


def _ticket_create_command(
    installed: _InstalledWheel,
    base_url: str,
    command_id: object,
) -> tuple[str | Path, ...]:
    return (
        installed.binary_directory / "ctl",
        "--base-url",
        base_url,
        "ticket",
        "create",
        "--command-id",
        str(command_id),
        "--initial-custodian-id",
        str(uuid4()),
        "--priority",
        "P1",
        "--source-kind",
        "packaging-test",
        "--source-ref",
        "test:installed-wheel",
        "--title",
        "Installed wheel durable queue",
    )


@contextmanager
def _health_server() -> Iterator[tuple[str, list[bytes]]]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    requests: list[bytes] = []
    thread = Thread(target=_serve_health, args=(listener, requests), daemon=True)
    thread.start()
    host, port = cast(tuple[str, int], listener.getsockname())
    try:
        yield f"http://{host}:{port}", requests
    finally:
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()


def _serve_health(listener: socket.socket, requests: list[bytes]) -> None:
    connection, _ = listener.accept()
    with connection:
        requests.append(connection.recv(8192))
        payload = json.dumps(_health_payload(), separators=(",", ":")).encode()
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(payload)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + payload
        )
        connection.sendall(response)


def _health_payload() -> dict[str, object]:
    observed = "2026-07-24T00:00:00Z"
    contributor = {
        "key": "durability",
        "status": "HEALTHY",
        "watermark": 0,
        "threshold_seconds": 30,
        "observed_at": observed,
        "owner": "packaging-fixture",
        "reason": "synthetic installed-wheel query",
    }
    dimension = {"status": "HEALTHY", "contributors": [contributor]}
    return {
        "schema_id": "ctower.health/v1",
        "status": "HEALTHY",
        "observed_at": observed,
        "availability": dimension,
        "completeness": dimension,
        "integrity": dimension,
    }


def _unused_base_url() -> str:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{cast(tuple[str, int], candidate.getsockname())[1]}"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(candidate.relative_to(root)): candidate.read_bytes()
        for candidate in root.rglob("*")
        if candidate.is_file()
    }
