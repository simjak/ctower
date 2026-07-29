"""Build one external installed ctowerctl runtime from the current working tree."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import venv
from collections.abc import Mapping, Sequence
from pathlib import Path

__all__ = ["install_ctowerctl"]

ROOT = Path(__file__).parents[4]


def install_ctowerctl(workspace: Path) -> Path:
    """Install the current wheel and pack tree without resolving dependencies."""

    source = workspace / "source"
    _copy_wheel_source(source)
    wheel_directory = workspace / "wheel"
    wheel_directory.mkdir()
    _checked(
        (sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", wheel_directory),
        cwd=source,
        timeout=180,
    )
    wheels = tuple(wheel_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("wheel build must emit exactly one artifact")
    environment_root = workspace / "environment"
    venv.EnvBuilder(with_pip=True).create(environment_root)
    shutil.copytree(ROOT / "packs", workspace / "packs")
    _bind_verifier_site(environment_root)
    binary_directory = environment_root / "bin"
    _checked(
        (
            binary_directory / "python",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            wheels[0],
        ),
        cwd=workspace,
        timeout=120,
    )
    executable = (binary_directory / "ctowerctl").resolve(strict=True)
    if not executable.is_relative_to(workspace):
        raise RuntimeError("installed ctowerctl escaped its disposable runtime")
    return executable


def _bind_verifier_site(environment_root: Path) -> None:
    site_packages = tuple((environment_root / "lib").glob("python*/site-packages"))
    if len(site_packages) != 1:
        raise RuntimeError("installed environment must have exactly one package directory")
    verifier_site = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    (site_packages[0] / "ctower-verifier-site.pth").write_text(
        f"{verifier_site}\n",
        encoding="utf-8",
    )


def _copy_wheel_source(source: Path) -> None:
    source.mkdir()
    for relative in (
        "LICENSE",
        "pyproject.toml",
        "tools/__init__.py",
        "tools/process_execution.py",
    ):
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


def _checked(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    timeout: int,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed verifier-owned build command
        tuple(str(argument) for argument in command),
        cwd=cwd,
        env=_build_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def _build_environment() -> Mapping[str, str]:
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment
