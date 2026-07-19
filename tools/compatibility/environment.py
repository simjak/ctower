from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .models_core import (
    CompatibilityError,
    CompatibilityMatrix,
    EnvironmentVariable,
    PythonVersion,
)

__all__ = [
    "bootstrap_environment",
    "container_prefix",
    "copy_probe_package",
    "docker_environment",
    "host_environment",
    "macos_architecture",
    "macos_python_request",
]

_DOCKER_CONNECTIVITY = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "DOCKER_CONFIG",
)


def copy_probe_package(run_root: Path) -> Path:
    destination = run_root / "package" / "ctower_compat_probe"
    destination.mkdir(parents=True, mode=0o700)
    source = Path(__file__).parent
    (destination / "__init__.py").write_text("", encoding="utf-8")
    for filename in (
        "models_core.py",
        "models_probe.py",
        "process.py",
        "probe.py",
    ):
        shutil.copyfile(source / filename, destination / filename)
    return destination.parent


def bootstrap_environment(
    scratch: Path, matrix: CompatibilityMatrix
) -> tuple[EnvironmentVariable, ...]:
    values = {
        "HOME": str(scratch / "bootstrap-home"),
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "SOURCE_DATE_EPOCH": "0",
        "TMPDIR": str(scratch / "bootstrap-tmp"),
        "UV_CACHE_DIR": str(scratch / "uv-cache"),
        "UV_NO_CONFIG": "1",
        "UV_TOOL_BIN_DIR": str(scratch / "uv-bin"),
        "UV_TOOL_DIR": str(scratch / "uv-tools"),
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CTOWER_TELEMETRY_CONTEXT": _telemetry_json(matrix),
    }
    for directory in (scratch / "bootstrap-home", scratch / "bootstrap-tmp"):
        directory.mkdir(mode=0o700)
    return _environment(values)


def host_environment(
    run_root: Path, package_root: Path, matrix: CompatibilityMatrix
) -> tuple[EnvironmentVariable, ...]:
    values = {
        "HOME": str(run_root / "home"),
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONPATH": str(package_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SOURCE_DATE_EPOCH": "0",
        "TMPDIR": str(run_root / "tmp"),
        "UV_CACHE_DIR": str(run_root.parent / "uv-cache"),
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": str(run_root.parent / "managed-python"),
        "UV_TOOL_BIN_DIR": str(run_root.parent / "uv-bin"),
        "UV_TOOL_DIR": str(run_root.parent / "uv-tools"),
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CTOWER_TELEMETRY_CONTEXT": _telemetry_json(matrix),
    }
    for directory in (run_root / "home", run_root / "tmp"):
        directory.mkdir(mode=0o700)
    return _environment(values)


def docker_environment(docker: str) -> tuple[EnvironmentVariable, ...]:
    values = {"PATH": f"{Path(docker).parent}:/usr/local/bin:/usr/bin:/bin"}
    developer_home = os.environ.get("HOME")
    if developer_home:
        values["HOME"] = developer_home
    for name in _DOCKER_CONNECTIVITY:
        value = os.environ.get(name)
        if value:
            values[name] = value
    return _environment(values)


def container_prefix(
    docker: str, container_id: str, matrix: CompatibilityMatrix
) -> tuple[str, ...]:
    return (
        docker,
        "exec",
        container_id,
        "/usr/bin/env",
        "-i",
        "HOME=/fixture/home",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH=/fixture/package",
        "PYTHONDONTWRITEBYTECODE=1",
        "SOURCE_DATE_EPOCH=0",
        "TMPDIR=/fixture/tmp",
        "PIP_CONFIG_FILE=/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK=1",
        f"CTOWER_TELEMETRY_CONTEXT={_telemetry_json(matrix)}",
    )


def macos_python_request(version: PythonVersion, machine: str) -> str:
    return f"cpython-{version}-macos-{macos_architecture(machine)}-none"


def macos_architecture(machine: str) -> str:
    architectures = {
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
    }
    architecture = architectures.get(machine.lower())
    if architecture is None:
        raise CompatibilityError(f"unsupported macOS compatibility architecture: {machine}")
    return architecture


def _environment(values: dict[str, str]) -> tuple[EnvironmentVariable, ...]:
    return tuple(
        EnvironmentVariable(name=name, value=value) for name, value in sorted(values.items())
    )


def _telemetry_json(matrix: CompatibilityMatrix) -> str:
    return json.dumps(
        matrix.telemetry.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
    )
