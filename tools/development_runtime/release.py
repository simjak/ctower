"""Verified release staging and crash-resumable pointer transitions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from tools.release_manifest import verify_manifest

__all__ = ["install_release", "release_home", "rollback"]


@dataclass(frozen=True, slots=True)
class _ReleaseTransition:
    operation: Literal["install", "rollback"]
    old_current: Path | None
    old_previous: Path | None
    new_current: Path
    new_previous: Path | None


def install_release(
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
    source_root: Path,
) -> None:
    """Verify, stage, and select one unprivileged release."""

    home = release_home()
    recovered = _recover_release_transition(home)
    if recovered is not None:
        if recovered != "install":
            raise RuntimeError("recovered an interrupted rollback; rerun install-release")
        return
    current_manifest = home / "current/manifest.json"
    predecessor = (
        None
        if not current_manifest.is_file()
        else f"sha256:{hashlib.sha256(current_manifest.read_bytes()).hexdigest()}"
    )
    manifest = verify_manifest(
        manifest_path,
        wheel,
        packs,
        source_root=source_root,
        python_executable=python,
        predecessor=predecessor,
    )
    release_id = f"{manifest.source_commit[:12]}-{manifest.wheel.sha256[7:19]}"
    release = home / "releases" / release_id
    if not release.exists():
        _stage_release(release, wheel, manifest_path, packs, python)
    else:
        verify_manifest(
            release / "manifest.json",
            release / wheel.name,
            release / "packs",
            source_root=source_root,
            python_executable=python,
            predecessor=predecessor,
        )
    _select_installed_release(home, release)
    _restart_release_services(required=False)
    _release_transition_path(home).unlink()


def rollback() -> None:
    """Select the exact predecessor and restart the same-artifact services."""

    home = release_home()
    recovered = _recover_release_transition(home)
    if recovered is not None:
        if recovered != "rollback":
            raise RuntimeError("recovered an interrupted install; rerun rollback")
        return
    current = home / "current"
    previous = home / "previous"
    if not current.is_symlink() or not previous.is_symlink():
        raise RuntimeError("rollback requires both current and previous verified releases")
    old_current = current.resolve(strict=True)
    old_previous = previous.resolve(strict=True)
    if old_current == old_previous:
        raise RuntimeError("rollback current and previous pointers resolve to the same release")
    transition = _ReleaseTransition(
        "rollback",
        old_current,
        old_previous,
        old_previous,
        old_current,
    )
    _commit_release_transition(home, transition)
    _restart_release_services(required=True)
    _release_transition_path(home).unlink()


def release_home() -> Path:
    return _data_home() / "ctower-development"


def _select_installed_release(home: Path, release: Path) -> None:
    current = home / "current"
    previous = home / "previous"
    old_current = current.resolve(strict=True) if current.is_symlink() else None
    old_previous = previous.resolve(strict=True) if previous.is_symlink() else None
    if old_current is None and old_previous is not None:
        raise RuntimeError("release inventory has previous without current")
    _commit_release_transition(
        home,
        _ReleaseTransition("install", old_current, old_previous, release, old_current),
    )


def _commit_release_transition(home: Path, transition: _ReleaseTransition) -> None:
    _write_release_transition(home, transition)
    _apply_release_transition(home, transition)


def _stage_release(
    release: Path,
    wheel: Path,
    manifest_path: Path,
    packs: Path,
    python: Path,
) -> None:
    releases = release.parent
    releases.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"{release.name}.staging-", dir=releases
    ) as staging_name:
        staging = Path(staging_name)
        shutil.copy2(wheel, staging / wheel.name)
        shutil.copy2(manifest_path, staging / "manifest.json")
        shutil.copytree(packs, staging / "packs")
        _run([str(python.resolve(strict=True)), "-m", "venv", str(staging / "venv")])
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("uv is required to install the verified development artifact")
        _run(
            [
                str(Path(uv).resolve(strict=True)),
                "pip",
                "install",
                "--python",
                str(staging / "venv/bin/python"),
                str(staging / wheel.name),
            ]
        )
        freeze = _run(
            [
                str(staging / "venv/bin/python"),
                "-m",
                "pip",
                "freeze",
                "--all",
            ],
            capture=True,
        )
        (staging / "installed-distributions.txt").write_text(freeze, encoding="utf-8")
        staging.replace(release)


def _release_transition_path(home: Path) -> Path:
    return home / "release-transition.json"


def _release_transition_temporary_path(home: Path) -> Path:
    return home / "release-transition.json.tmp"


def _write_release_transition(home: Path, transition: _ReleaseTransition) -> None:
    path = _release_transition_path(home)
    if path.exists():
        raise FileExistsError("a release transition already requires recovery")
    payload = {
        "schema": "ctower.development-release-transition/v1",
        "operation": transition.operation,
        "old_current": None if transition.old_current is None else str(transition.old_current),
        "old_previous": None if transition.old_previous is None else str(transition.old_previous),
        "new_current": str(transition.new_current),
        "new_previous": None if transition.new_previous is None else str(transition.new_previous),
    }
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = _release_transition_temporary_path(home)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _recover_release_transition(
    home: Path,
) -> Literal["install", "rollback"] | None:
    path = _release_transition_path(home)
    if not path.exists():
        _release_transition_temporary_path(home).unlink(missing_ok=True)
        return None
    transition = _load_release_transition(home, path)
    _apply_release_transition(home, transition)
    _restart_release_services(required=transition.operation == "rollback")
    path.unlink()
    return transition.operation


def _load_release_transition(home: Path, path: Path) -> _ReleaseTransition:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema",
        "operation",
        "old_current",
        "old_previous",
        "new_current",
        "new_previous",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise RuntimeError("release transition has an unknown shape")
    if payload["schema"] != "ctower.development-release-transition/v1":
        raise RuntimeError("release transition has an unknown schema")
    operation_value = payload["operation"]
    if operation_value not in {"install", "rollback"}:
        raise RuntimeError("release transition has an unknown operation")
    operation = cast(Literal["install", "rollback"], operation_value)
    transition = _ReleaseTransition(
        operation,
        _release_target(home, payload["old_current"]),
        _release_target(home, payload["old_previous"]),
        _required_release_target(home, payload["new_current"]),
        _release_target(home, payload["new_previous"]),
    )
    _validate_transition(transition)
    return transition


def _validate_transition(transition: _ReleaseTransition) -> None:
    if transition.operation == "install" and transition.new_previous != transition.old_current:
        raise RuntimeError("install transition does not preserve its predecessor")
    if transition.operation == "rollback" and (
        transition.new_current != transition.old_previous
        or transition.new_previous != transition.old_current
    ):
        raise RuntimeError("rollback transition does not exchange exact releases")


def _required_release_target(home: Path, value: object) -> Path:
    target = _release_target(home, value)
    if target is None:
        raise RuntimeError("release transition requires a current target")
    return target


def _release_target(home: Path, value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("release transition target must be an exact path")
    target = Path(value).resolve(strict=True)
    releases = (home / "releases").resolve(strict=True)
    if target.parent != releases or not target.is_dir():
        raise RuntimeError("release transition target is outside the release inventory")
    return target


def _apply_release_transition(home: Path, transition: _ReleaseTransition) -> None:
    current = home / "current"
    previous = home / "previous"
    if transition.new_previous is not None:
        _replace_symlink(previous, transition.new_previous)
    elif previous.exists() or previous.is_symlink():
        raise RuntimeError("first release found an unexplained previous pointer")
    _replace_symlink(current, transition.new_current)


def _replace_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = link.with_name(link.name + ".next")
    if temporary.exists() or temporary.is_symlink():
        if not temporary.is_symlink() or temporary.resolve(strict=True) != target.resolve(
            strict=True
        ):
            raise FileExistsError(f"stale release pointer requires operator review: {temporary}")
        temporary.replace(link)
        return
    temporary.symlink_to(target)
    temporary.replace(link)


def _restart_release_services(*, required: bool) -> None:
    if not _unit_known("ctower-development-api.service"):
        if required:
            raise RuntimeError("rollback requires installed development service units")
        return
    _systemctl(
        "restart",
        "ctower-development-api.service",
        "ctower-development-worker.service",
    )


def _unit_known(name: str) -> bool:
    result = subprocess.run(  # noqa: S603 - exact user-unit query
        ["/usr/bin/systemctl", "--user", "cat", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


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


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
