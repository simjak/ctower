"""Verified one-time installation for the persistent E2 shadow runtime."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import tools.process_execution as process_execution  # noqa: PLR0402
from tools.runtime_manifest import verify_manifest

__all__ = ["install_runtime", "runtime_home"]

_CREATE_ENVIRONMENT_TIMEOUT_SECONDS = 60.0
_INSTALL_TIMEOUT_SECONDS = 300.0
_VERIFY_TIMEOUT_SECONDS = 60.0


def install_runtime(
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
    source_root: Path,
) -> None:
    """Install one verified artifact directly at its permanent runtime path."""

    home = runtime_home()
    if home.exists() or home.is_symlink():
        raise FileExistsError("the persistent runtime is already installed")
    verify_manifest(
        manifest_path,
        wheel,
        packs,
        source_root=source_root,
        python_executable=python,
    )
    home.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.mkdir(mode=0o700)
    try:
        installed_wheel = home / wheel.name
        shutil.copy2(wheel, installed_wheel)
        shutil.copy2(manifest_path, home / "manifest.json")
        shutil.copytree(packs, home / "packs")
        freeze = _install_environment(home, installed_wheel, python)
        (home / "installed-distributions.txt").write_text(freeze, encoding="utf-8")
    except Exception:
        shutil.rmtree(home)
        raise


def runtime_home() -> Path:
    """Return the fixed installation selected by the Part A service units."""

    return _data_home() / "ctower-development" / "runtime"


def _install_environment(home: Path, installed_wheel: Path, python: Path) -> str:
    environment_python = home / "venv/bin/python"
    _run(
        [str(python.resolve(strict=True)), "-m", "venv", str(home / "venv")],
        timeout_seconds=_CREATE_ENVIRONMENT_TIMEOUT_SECONDS,
    )
    uv = _uv_path()
    _run(
        [uv, "pip", "install", "--python", str(environment_python), str(installed_wheel)],
        timeout_seconds=_INSTALL_TIMEOUT_SECONDS,
    )
    _run(
        [uv, "pip", "check", "--python", str(environment_python)],
        timeout_seconds=_VERIFY_TIMEOUT_SECONDS,
    )
    freeze = _run(
        [uv, "pip", "freeze", "--python", str(environment_python)],
        timeout_seconds=_VERIFY_TIMEOUT_SECONDS,
        capture=True,
    )
    _run(
        [str(home / "venv/bin/ctower-private-vps"), "--help"],
        timeout_seconds=_VERIFY_TIMEOUT_SECONDS,
        capture=True,
    )
    return freeze


def _run(
    arguments: list[str],
    *,
    timeout_seconds: float,
    capture: bool = False,
) -> str:
    result = process_execution.run(
        arguments,
        timeout_seconds=timeout_seconds,
        check=True,
        capture_output=capture,
    )
    return (result.stdout or "") if capture else ""


def _uv_path() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to install the verified development artifact")
    return uv


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
