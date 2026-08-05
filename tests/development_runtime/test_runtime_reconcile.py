"""Orphaned runtime-replacement cleanup proofs for the E2 development runtime."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import tools.development_runtime.installation as installation  # noqa: PLR0402
import tools.development_runtime.interface as runtime_interface
from tools.development_runtime import reconcile

_LOCK_BLOCK_SECONDS = 0.2
_PROCESS_TIMEOUT_SECONDS = 10.0
_REPOSITORY_ROOT = Path(__file__).parents[2]

_LOCK_HOLDER = """
import fcntl
import os
import sys
import time

directory = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
fcntl.flock(directory, fcntl.LOCK_EX)
open(sys.argv[2], "w").close()
while not os.path.exists(sys.argv[3]):
    time.sleep(0.01)
os.close(directory)
"""


def test_reconcile_removes_an_orphaned_replacement_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(installation, "_data_home", lambda: tmp_path / "data")
    home = installation.runtime_home()
    _write_runtime_dir(home)
    orphan = home.with_name("runtime-replacement-orphan")
    _write_runtime_dir(orphan)

    result = reconcile.reconcile_runtime()

    assert result["removed"] == ["runtime-replacement-orphan"]
    assert not orphan.exists()
    assert home.is_dir() and not home.is_symlink()


def test_reconcile_preserves_current_and_previous_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(installation, "_data_home", lambda: tmp_path / "data")
    home = installation.runtime_home()
    previous = installation.runtime_previous()
    current_target = home.with_name("runtime-replacement-current")
    previous_target = home.with_name("runtime-replacement-previous")
    _write_runtime_dir(current_target)
    _write_runtime_dir(previous_target)
    home.symlink_to(current_target.name, target_is_directory=True)
    previous.symlink_to(previous_target.name, target_is_directory=True)
    orphan = home.with_name("runtime-replacement-orphan")
    _write_runtime_dir(orphan)

    result = reconcile.reconcile_runtime()

    assert result["removed"] == ["runtime-replacement-orphan"]
    assert not orphan.exists()
    assert current_target.is_dir()
    assert previous_target.is_dir()
    assert home.resolve(strict=True) == current_target
    assert previous.resolve(strict=True) == previous_target


def test_reconcile_reports_nothing_when_runtime_storage_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(installation, "_data_home", lambda: tmp_path / "data")

    result = reconcile.reconcile_runtime()

    assert result == {"schema": "ctower.runtime-reconcile/v1", "removed": []}


def test_reconcile_waits_for_a_concurrent_runtime_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(installation, "_data_home", lambda: tmp_path / "data")
    home = installation.runtime_home()
    home.parent.mkdir(parents=True)
    ready = tmp_path / "lock-ready"
    release = tmp_path / "lock-release"
    holder = subprocess.Popen(  # noqa: S603 - fixture-owned interpreter and paths
        [sys.executable, "-c", _LOCK_HOLDER, str(home.parent), str(ready), str(release)],
        cwd=_REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for_path(ready, holder)

    results: list[dict[str, object]] = []
    thread = threading.Thread(target=lambda: results.append(reconcile.reconcile_runtime()))
    started = time.monotonic()
    thread.start()
    time.sleep(_LOCK_BLOCK_SECONDS)
    assert thread.is_alive()
    release.touch()
    thread.join(timeout=_PROCESS_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert time.monotonic() - started >= _LOCK_BLOCK_SECONDS
    assert results == [{"schema": "ctower.runtime-reconcile/v1", "removed": []}]
    _assert_process_succeeded(holder)


def test_reconcile_runtime_is_wired_into_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_reconcile() -> dict[str, object]:
        calls.append("reconcile")
        return {"schema": "ctower.runtime-reconcile/v1", "removed": []}

    monkeypatch.setattr(runtime_interface, "reconcile_runtime", fake_reconcile)
    monkeypatch.setattr(sys, "argv", ["ctower-private-vps", "reconcile-runtime"])

    runtime_interface.main()

    assert calls == ["reconcile"]


def _write_runtime_dir(home: Path) -> None:
    entrypoint = home / "venv/bin/ctower-private-vps"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text('#!/bin/sh\nprintf "ok\\n"\n', encoding="utf-8")
    entrypoint.chmod(0o700)
    (home / "manifest.json").write_text('{"version": "fixture"}\n', encoding="utf-8")


def _wait_for_path(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"lock-holder subprocess exited before {path.name}: "
                f"returncode={process.returncode}, stdout={stdout!r}, stderr={stderr!r}"
            )
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for subprocess boundary: {path.name}")


def _assert_process_succeeded(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=_PROCESS_TIMEOUT_SECONDS)
    assert process.returncode == 0, (
        f"lock-holder subprocess failed with {process.returncode}: "
        f"stdout={stdout!r}, stderr={stderr!r}"
    )
