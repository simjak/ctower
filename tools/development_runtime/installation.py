"""Verified one-time installation for the persistent E2 shadow runtime."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import tools.process_execution as process_execution  # noqa: PLR0402
from tools.runtime_manifest import verify_manifest

__all__ = ["install_runtime", "rollback_runtime", "runtime_home", "runtime_previous"]

_CREATE_ENVIRONMENT_TIMEOUT_SECONDS = 60.0
_INSTALL_TIMEOUT_SECONDS = 300.0
_VERIFY_TIMEOUT_SECONDS = 60.0
_AT_FDCWD = -100
_RENAME_EXCHANGE = 2


class _RenameAt2(Protocol):
    argtypes: object
    restype: object

    def __call__(
        self,
        old_directory: int,
        old_path: bytes,
        new_directory: int,
        new_path: bytes,
        flags: int,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class _RuntimeChangeLock:
    parent: Path


def install_runtime(
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
    source_root: Path,
    *,
    replace: bool = False,
) -> None:
    """Install one verified artifact, optionally replacing an existing runtime."""

    home = runtime_home()
    if replace:
        _replace_runtime(home, wheel, manifest_path, packs, python, source_root)
        return
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
    _create_runtime(home, wheel, manifest_path, packs, python)


def rollback_runtime() -> None:
    """Atomically exchange the current runtime with its retained predecessor."""

    current = runtime_home()
    previous = runtime_previous()
    with _serialize_runtime_changes(current):
        _require_installed_runtime(current, label="current")
        _require_installed_runtime(previous, label="previous")
        _exchange_paths(current, previous)


def runtime_previous() -> Path:
    """Return the predecessor pathname used by replace and rollback."""

    return runtime_home().with_name("runtime-previous")


def _replace_runtime(
    home: Path,
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
    source_root: Path,
) -> None:
    with _serialize_runtime_changes(home) as lock:
        _require_installed_runtime(home, label="current")
        verify_manifest(
            manifest_path,
            wheel,
            packs,
            source_root=source_root,
            python_executable=python,
        )
        replacement = home.with_name(f"runtime-replacement-{uuid4().hex}")
        _create_runtime(replacement, wheel, manifest_path, packs, python)
        previous = runtime_previous()
        try:
            _discard_previous(previous, current=home, lock=lock)
            previous.symlink_to(replacement.name, target_is_directory=True)
            _exchange_paths(home, previous)
        except Exception:
            if previous.is_symlink() and previous.readlink() == Path(replacement.name):
                previous.unlink()
            if replacement.exists():
                shutil.rmtree(replacement)
            raise


@contextmanager
def _serialize_runtime_changes(home: Path) -> Iterator[_RuntimeChangeLock]:
    """Block concurrent runtime-changing verbs until this operation exits."""

    try:
        directory = os.open(home.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except (FileNotFoundError, NotADirectoryError) as error:
        raise FileNotFoundError("the current persistent runtime is not installed") from error
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        yield _RuntimeChangeLock(parent=home.parent)
    finally:
        os.close(directory)


def _create_runtime(
    home: Path,
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
) -> None:
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


def _require_installed_runtime(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"the {label} persistent runtime is not installed")
    entrypoint = path / "venv/bin/ctower-private-vps"
    if not (path / "manifest.json").is_file() or not entrypoint.is_file():
        raise RuntimeError(f"the {label} persistent runtime is incomplete")
    if not os.access(entrypoint, os.X_OK):
        raise RuntimeError(f"the {label} persistent runtime entry point is not executable")


def _discard_previous(
    previous: Path,
    *,
    current: Path,
    lock: _RuntimeChangeLock | None = None,
) -> None:
    if lock is None or lock.parent != previous.parent:
        raise RuntimeError("runtime predecessor discard requires the runtime change lock")
    if previous.is_symlink():
        target = previous.readlink()
        if (
            target.is_absolute()
            or target.parent != Path()
            or not target.name.startswith("runtime-replacement-")
        ):
            raise RuntimeError("the retained runtime predecessor has an unmanaged target")
        managed_target = previous.parent / target
        if managed_target.resolve(strict=True) == current.resolve(strict=True):
            raise RuntimeError("the retained runtime predecessor selects the current runtime")
        previous.unlink()
        shutil.rmtree(managed_target)
    elif previous.is_dir():
        shutil.rmtree(previous)
    elif previous.exists():
        raise RuntimeError("the retained runtime predecessor is not a directory or symlink")


def _exchange_paths(current: Path, previous: Path) -> None:
    """Atomically exchange two same-filesystem pathnames without a missing-name gap."""

    library = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = cast(_RenameAt2, library.renameat2)
    except AttributeError as error:
        raise OSError(
            errno.ENOSYS,
            "atomic runtime replacement requires renameat2(RENAME_EXCHANGE)",
        ) from error
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    if renameat2(
        _AT_FDCWD,
        os.fsencode(current),
        _AT_FDCWD,
        os.fsencode(previous),
        _RENAME_EXCHANGE,
    ):
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), f"{current} <-> {previous}")


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
