"""Atomic replacement and rollback proofs for the E2 development runtime."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import pytest

import tools.development_runtime.installation as installation  # noqa: PLR0402
import tools.development_runtime.interface as runtime_interface

__all__: tuple[str, ...] = ()

_RETAINED_RUNTIME_COUNT = 2
_LOCK_BLOCK_SECONDS = 0.2
_PROCESS_TIMEOUT_SECONDS = 10.0
_REPOSITORY_ROOT = Path(__file__).parents[2]

_RUNTIME_OPERATION = """
from pathlib import Path
import sys
import time

import tools.development_runtime.installation as installation

(
    operation,
    data_home_value,
    uv_value,
    wheel_value,
    manifest_value,
    packs_value,
    python_value,
    source_root_value,
    block_at,
    ready_value,
    release_value,
) = sys.argv[1:]
data_home = Path(data_home_value)
installation._data_home = lambda: data_home
installation._uv_path = lambda: uv_value

def wait_at_boundary() -> None:
    Path(ready_value).write_text("ready", encoding="utf-8")
    release = Path(release_value)
    while not release.exists():
        time.sleep(0.01)

if block_at == "verify":
    installation.verify_manifest = lambda *_args, **_kwargs: wait_at_boundary()
else:
    installation.verify_manifest = lambda *_args, **_kwargs: None

if block_at == "exchange":
    exchange = installation._exchange_paths
    def blocked_exchange(current: Path, previous: Path) -> None:
        wait_at_boundary()
        exchange(current, previous)
    installation._exchange_paths = blocked_exchange

if operation == "replace":
    installation.install_runtime(
        Path(wheel_value),
        Path(manifest_value),
        Path(packs_value),
        Path(python_value),
        Path(source_root_value),
        replace=True,
    )
else:
    installation.rollback_runtime()
"""


@dataclass(frozen=True, slots=True)
class _InstallInputs:
    wheel: Path
    manifest: Path
    packs: Path
    python: Path
    source_root: Path


def test_replace_keeps_old_runtime_when_artifact_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    inputs.wheel.unlink()

    with pytest.raises(FileNotFoundError, match=r"new\.whl"):
        _replace(inputs)

    _assert_old_serving()
    assert _replacement_homes() == []


def test_replace_keeps_old_runtime_when_manifest_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        installation,
        "verify_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("injected manifest verification refusal")
        ),
    )

    with pytest.raises(ValueError, match="manifest verification refusal"):
        _replace(inputs)

    _assert_old_serving()
    assert _replacement_homes() == []


def test_replace_keeps_old_runtime_when_installed_entrypoint_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path, entrypoint_exit=23)

    with pytest.raises(subprocess.CalledProcessError):
        _replace(inputs)

    _assert_old_serving()
    assert _replacement_homes() == []


def test_replace_keeps_old_runtime_when_swap_is_interrupted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        installation,
        "_exchange_paths",
        lambda *_args: (_ for _ in ()).throw(
            OSError("injected swap interruption before renameat2")
        ),
    )

    with pytest.raises(OSError, match="swap interruption"):
        _replace(inputs)

    _assert_old_serving()
    assert not installation.runtime_previous().exists()
    assert _replacement_homes() == []


def test_replace_executes_entrypoint_before_atomic_swap_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    exchange = installation._exchange_paths
    observed: list[tuple[Path, Path]] = []

    def checked_exchange(current: Path, previous: Path) -> None:
        candidate = previous.resolve(strict=True)
        marker = candidate / "venv/bin/entrypoint-executed"
        assert marker.read_text(encoding="utf-8") == "executed"
        observed.append((current, previous))
        exchange(current, previous)

    monkeypatch.setattr(installation, "_exchange_paths", checked_exchange)

    _replace(inputs)

    current = installation.runtime_home()
    previous = installation.runtime_previous()
    assert observed == [(current, previous)]
    assert current.is_symlink()
    assert _manifest_version(current) == "new"
    assert _entrypoint_version(current) == "new"
    assert _manifest_version(previous) == "old"
    assert _entrypoint_version(previous) == "old"

    monkeypatch.setattr(installation, "_exchange_paths", exchange)
    monkeypatch.setattr(sys, "argv", ["ctower-private-vps", "rollback-runtime"])
    runtime_interface.main()

    assert not current.is_symlink()
    assert _manifest_version(current) == "old"
    assert _entrypoint_version(current) == "old"
    assert previous.is_symlink()
    assert _manifest_version(previous) == "new"


def test_linux_exchange_swaps_existing_pathnames_without_missing_runtime(
    tmp_path: Path,
) -> None:
    current = tmp_path / "runtime"
    previous = tmp_path / "runtime-previous"
    current.mkdir()
    previous.symlink_to("runtime-new", target_is_directory=True)
    (tmp_path / "runtime-new").mkdir()

    installation._exchange_paths(current, previous)

    assert current.is_symlink()
    assert current.resolve(strict=True) == tmp_path / "runtime-new"
    assert previous.is_dir()
    assert not previous.is_symlink()


def test_three_replacements_retain_only_current_and_immediate_predecessor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)

    for version in ("new-1", "new-2", "new-3"):
        inputs.manifest.write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
        _replace(inputs)

    assert _manifest_version(installation.runtime_home()) == "new-3"
    assert _manifest_version(installation.runtime_previous()) == "new-2"
    assert len(_replacement_homes()) == _RETAINED_RUNTIME_COUNT


def test_runtime_cli_wires_replace_and_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _inputs(tmp_path)
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        runtime_interface,
        "install_runtime",
        lambda *_args, replace=False: calls.append(("install", replace)),
    )
    monkeypatch.setattr(
        runtime_interface,
        "rollback_runtime",
        lambda: calls.append(("rollback", False)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ctower-private-vps",
            "install-runtime",
            "--wheel",
            str(inputs.wheel),
            "--manifest",
            str(inputs.manifest),
            "--packs",
            str(inputs.packs),
            "--python",
            str(inputs.python),
            "--source-root",
            str(inputs.source_root),
            "--replace",
        ],
    )

    runtime_interface.main()
    monkeypatch.setattr(sys, "argv", ["ctower-private-vps", "rollback-runtime"])
    runtime_interface.main()

    assert calls == [("install", True), ("rollback", False)]


def test_predecessor_discard_requires_the_matching_runtime_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _runtime_fixture(monkeypatch, tmp_path)
    previous = installation.runtime_previous()
    current = installation.runtime_home()

    with pytest.raises(RuntimeError, match="requires the runtime change lock"):
        installation._discard_previous(previous, current=current)
    with pytest.raises(RuntimeError, match="requires the runtime change lock"):
        installation._discard_previous(
            previous,
            current=current,
            lock=installation._RuntimeChangeLock(parent=tmp_path),
        )

    _assert_old_serving()


def test_rollback_waits_for_replace_and_remains_reversible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    ready = tmp_path / "replace-ready"
    release = tmp_path / "replace-release"
    replacing = _start_runtime_operation(
        inputs,
        data_home=tmp_path / "data",
        block_at="verify",
        ready=ready,
        release=release,
    )
    _wait_for_path(ready, replacing)

    started = time.monotonic()
    rolling_back = _start_runtime_operation(
        inputs,
        data_home=tmp_path / "data",
        operation="rollback",
    )
    time.sleep(_LOCK_BLOCK_SECONDS)
    assert rolling_back.poll() is None
    release.touch()
    _assert_process_succeeded(replacing)
    _assert_process_succeeded(rolling_back)
    assert time.monotonic() - started >= _LOCK_BLOCK_SECONDS

    _assert_runtime_version(current="old", previous="new")
    installation.rollback_runtime()
    _assert_runtime_version(current="new", previous="old")


def test_replace_waits_for_rollback_and_remains_reversible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    _replace(inputs)
    inputs.manifest.write_text('{"version": "new-2"}\n', encoding="utf-8")
    _write_toolchain(inputs.python, tmp_path / "uv", entrypoint_exit=0, version="new-2")
    ready = tmp_path / "rollback-ready"
    release = tmp_path / "rollback-release"
    rolling_back = _start_runtime_operation(
        inputs,
        data_home=tmp_path / "data",
        operation="rollback",
        block_at="exchange",
        ready=ready,
        release=release,
    )
    _wait_for_path(ready, rolling_back)

    started = time.monotonic()
    replacing = _start_runtime_operation(inputs, data_home=tmp_path / "data")
    time.sleep(_LOCK_BLOCK_SECONDS)
    assert replacing.poll() is None
    release.touch()
    _assert_process_succeeded(rolling_back)
    _assert_process_succeeded(replacing)
    assert time.monotonic() - started >= _LOCK_BLOCK_SECONDS

    _assert_runtime_version(current="new-2", previous="old")
    installation.rollback_runtime()
    _assert_runtime_version(current="old", previous="new-2")


def test_runtime_change_lock_is_released_when_holder_is_killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _runtime_fixture(monkeypatch, tmp_path)
    ready = tmp_path / "replace-ready"
    release = tmp_path / "replace-release"
    holder = _start_runtime_operation(
        inputs,
        data_home=tmp_path / "data",
        block_at="verify",
        ready=ready,
        release=release,
    )
    _wait_for_path(ready, holder)

    holder.kill()
    holder.communicate(timeout=_PROCESS_TIMEOUT_SECONDS)
    assert holder.returncode is not None and holder.returncode < 0
    replacement = _start_runtime_operation(inputs, data_home=tmp_path / "data")
    _assert_process_succeeded(replacement)

    _assert_runtime_version(current="new", previous="old")
    installation.rollback_runtime()
    _assert_runtime_version(current="old", previous="new")


def _runtime_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    entrypoint_exit: int = 0,
) -> _InstallInputs:
    inputs = _inputs(tmp_path)
    _write_toolchain(inputs.python, tmp_path / "uv", entrypoint_exit=entrypoint_exit)
    inputs.wheel.write_bytes(b"new wheel")
    inputs.manifest.write_text('{"version": "new"}\n', encoding="utf-8")
    inputs.packs.mkdir()
    (inputs.packs / "pack.yaml").write_text("pack: new\n", encoding="utf-8")
    monkeypatch.setattr(installation, "_data_home", lambda: tmp_path / "data")
    monkeypatch.setattr(installation, "_uv_path", lambda: str(tmp_path / "uv"))
    monkeypatch.setattr(installation, "verify_manifest", lambda *_args, **_kwargs: None)
    _write_old_runtime(installation.runtime_home())
    return inputs


def _inputs(tmp_path: Path) -> _InstallInputs:
    return _InstallInputs(
        wheel=tmp_path / "new.whl",
        manifest=tmp_path / "new-manifest.json",
        packs=tmp_path / "packs",
        python=tmp_path / "python",
        source_root=tmp_path,
    )


def _write_toolchain(
    python: Path,
    uv: Path,
    *,
    entrypoint_exit: int,
    version: str = "new",
) -> None:
    python.write_text(
        '#!/bin/sh\nset -eu\nmkdir -p "$3/bin"\nln -s /bin/sh "$3/bin/python"\n',
        encoding="utf-8",
    )
    python.chmod(0o700)
    uv.write_text(
        f"""#!/bin/sh
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
        printf 'echo {version}\\n' >> "$entrypoint"
        printf 'printf executed > "$(dirname "$0")/entrypoint-executed"\\n' >> "$entrypoint"
        printf 'exit {entrypoint_exit}\\n' >> "$entrypoint"
        chmod 700 "$entrypoint"
        ;;
    check) ;;
    freeze) printf 'ctower-workspace==0.0.0\\n' ;;
esac
""",
        encoding="utf-8",
    )
    uv.chmod(0o700)


def _write_old_runtime(home: Path) -> None:
    entrypoint = home / "venv/bin/ctower-private-vps"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(
        '#!/bin/sh\ntest "$1" = "--help"\nprintf "old\\n"\n',
        encoding="utf-8",
    )
    entrypoint.chmod(0o700)
    (home / "manifest.json").write_text('{"version": "old"}\n', encoding="utf-8")


def _replace(inputs: _InstallInputs) -> None:
    installation.install_runtime(
        inputs.wheel,
        inputs.manifest,
        inputs.packs,
        inputs.python,
        inputs.source_root,
        replace=True,
    )


def _start_runtime_operation(
    inputs: _InstallInputs,
    *,
    data_home: Path,
    operation: Literal["replace", "rollback"] = "replace",
    block_at: Literal["none", "verify", "exchange"] = "none",
    ready: Path | None = None,
    release: Path | None = None,
) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603 - fixture-owned interpreter and paths
        [
            sys.executable,
            "-c",
            _RUNTIME_OPERATION,
            operation,
            str(data_home),
            str(inputs.python.parent / "uv"),
            str(inputs.wheel),
            str(inputs.manifest),
            str(inputs.packs),
            str(inputs.python),
            str(inputs.source_root),
            block_at,
            str(ready or ""),
            str(release or ""),
        ],
        cwd=_REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_path(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"runtime subprocess exited before {path.name}: "
                f"returncode={process.returncode}, stdout={stdout!r}, stderr={stderr!r}"
            )
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for subprocess boundary: {path.name}")


def _assert_process_succeeded(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=_PROCESS_TIMEOUT_SECONDS)
    assert process.returncode == 0, (
        f"runtime subprocess failed with {process.returncode}: stdout={stdout!r}, stderr={stderr!r}"
    )


def _assert_runtime_version(*, current: str, previous: str) -> None:
    home = installation.runtime_home()
    retained = installation.runtime_previous()
    assert _manifest_version(home) == current
    assert _entrypoint_version(home) == current
    assert _manifest_version(retained) == previous
    assert _entrypoint_version(retained) == previous


def _assert_old_serving() -> None:
    current = installation.runtime_home()
    assert _manifest_version(current) == "old"
    assert _entrypoint_version(current) == "old"


def _entrypoint_version(home: Path) -> str:
    result = subprocess.run(  # noqa: S603 - fixture-owned executable path
        [home / "venv/bin/ctower-private-vps", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _manifest_version(home: Path) -> str:
    payload = cast(dict[str, str], json.loads((home / "manifest.json").read_text(encoding="utf-8")))
    return payload["version"]


def _replacement_homes() -> list[Path]:
    return sorted(installation.runtime_home().parent.glob("runtime-replacement-*"))
