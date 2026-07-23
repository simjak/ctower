"""Cross-process locking and abrupt-process recovery evidence for the CLI spool."""

from __future__ import annotations

import fcntl
import importlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ctowerctl.spool import Spool, SpoolConfig

__all__: tuple[str, ...] = ()

_CHILD = """
import os
import time
from pathlib import Path
from uuid import UUID

from ctowerctl.spool import Spool, SpoolCommand, SpoolConfig

barrier = Path(os.environ["CT_SPOOL_BARRIER"])
deadline = time.monotonic() + 10
while not barrier.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("test barrier did not open")
    time.sleep(0.01)

spool = Spool.for_origin(
    "https://example.test/api",
    SpoolConfig(state_path=Path(os.environ["CT_SPOOL_STATE"])),
)
spool.enqueue(
    SpoolCommand(
        operation_id="createTicket",
        path_parameters={"tenant": "tenant-a"},
        request_body={"title": os.environ["CT_SPOOL_LABEL"]},
        command_id=UUID(os.environ["CT_SPOOL_COMMAND_ID"]),
    )
)
marker = os.environ.get("CT_SPOOL_READY")
if marker is not None:
    Path(marker).write_text("durable", encoding="utf-8")
    time.sleep(60)
"""

_KEYRING_MODULE = """
import os
from pathlib import Path


class Keyring:
    priority = 1.0

    def get_password(self, service, username):
        del service, username
        path = Path(os.environ["CT_SPOOL_KEYRING"])
        return path.read_text(encoding="ascii") if path.exists() else None

    def set_password(self, service, username, password):
        del service, username
        path = Path(os.environ["CT_SPOOL_KEYRING"])
        temporary = path.with_suffix(".new")
        temporary.write_text(password, encoding="ascii")
        os.replace(temporary, path)


Keyring.__module__ = "keyring.backends.SecretService"
_BACKEND = Keyring()


def get_keyring():
    return _BACKEND
"""


def test_two_subprocess_writers_serialize_into_one_authenticated_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    barrier = tmp_path / "start"
    module_dir, base_environment = _process_environment(tmp_path, state, barrier)
    command_ids = (uuid4(), uuid4())
    processes = [
        _spawn_writer(base_environment, command_id, f"writer-{index}")
        for index, command_id in enumerate(command_ids)
    ]

    barrier.write_text("go", encoding="utf-8")
    for process in processes:
        _assert_success(process)

    _install_process_keyring(monkeypatch, module_dir, base_environment)
    entries = Spool.for_origin(
        "https://example.test/api",
        SpoolConfig(state_path=state),
    ).list_entries()
    assert [entry.sequence for entry in entries] == [1, 2]
    assert {entry.command_id for entry in entries} == set(command_ids)


def test_sigkill_after_durable_append_releases_lock_and_preserves_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    barrier = tmp_path / "start"
    marker = tmp_path / "ready"
    module_dir, base_environment = _process_environment(tmp_path, state, barrier)
    command_id = uuid4()
    environment = base_environment | {"CT_SPOOL_READY": str(marker)}
    process = _spawn_writer(environment, command_id, "before-kill")
    barrier.write_text("go", encoding="utf-8")

    try:
        _wait_for_path(marker)
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    assert process.returncode == -signal.SIGKILL
    _install_process_keyring(monkeypatch, module_dir, base_environment)
    spool = Spool.for_origin(
        "https://example.test/api",
        SpoolConfig(state_path=state),
    )
    entries = spool.list_entries()
    assert len(entries) == 1
    assert entries[0].command_id == command_id
    assert spool.doctor().healthy


def test_contended_permanent_lock_times_out_with_unknown_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    barrier = tmp_path / "unused"
    module_dir, environment = _process_environment(tmp_path, state, barrier)
    _install_process_keyring(monkeypatch, module_dir, environment)
    spool = Spool.for_origin(
        "https://example.test/api",
        SpoolConfig(state_path=state, lock_timeout_seconds=0.01),
    )
    command_id = uuid4()
    environment["CT_SPOOL_COMMAND_ID"] = str(command_id)
    environment["CT_SPOOL_LABEL"] = "initialize"
    process = _spawn_writer(environment, command_id, "initialize")
    barrier.write_text("go", encoding="utf-8")
    _assert_success(process)
    root = next((state / "spool" / "v1").iterdir())
    lock_descriptor = os.open(root / "lock", os.O_RDWR)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = spool.status()
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)

    assert status.health == "state_unknown"
    assert status.reason_codes == ("lock_timeout",)
    assert status.pending_count is None


def _process_environment(
    tmp_path: Path,
    state: Path,
    barrier: Path,
) -> tuple[Path, dict[str, str]]:
    module_dir = tmp_path / "modules"
    module_dir.mkdir()
    (module_dir / "keyring.py").write_text(_KEYRING_MODULE, encoding="utf-8")
    repository = Path(__file__).resolve().parents[3]
    import_roots = (
        module_dir,
        repository / "apps" / "ctowerctl" / "src",
        repository / "generated" / "python",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "CT_SPOOL_BARRIER": str(barrier),
            "CT_SPOOL_KEYRING": str(tmp_path / "synthetic-keyring"),
            "CT_SPOOL_STATE": str(state),
            "PYTHONPATH": os.pathsep.join(
                (*map(str, import_roots), environment.get("PYTHONPATH", ""))
            ),
        }
    )
    return module_dir, environment


def _spawn_writer(
    base_environment: dict[str, str],
    command_id: UUID,
    label: str,
) -> subprocess.Popen[str]:
    environment = base_environment | {
        "CT_SPOOL_COMMAND_ID": str(command_id),
        "CT_SPOOL_LABEL": label,
    }
    return subprocess.Popen(  # noqa: S603
        (sys.executable, "-c", _CHILD),
        env=environment,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


def _assert_success(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, f"stdout={stdout!r}\nstderr={stderr!r}"


def _install_process_keyring(
    monkeypatch: pytest.MonkeyPatch,
    module_dir: Path,
    environment: dict[str, str],
) -> None:
    monkeypatch.setenv("CT_SPOOL_KEYRING", environment["CT_SPOOL_KEYRING"])
    monkeypatch.syspath_prepend(str(module_dir))
    monkeypatch.delitem(sys.modules, "keyring", raising=False)
    importlib.import_module("keyring")


def _wait_for_path(path: Path) -> None:
    deadline = time.monotonic() + 15
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError("child did not reach durable append")
        time.sleep(0.01)
