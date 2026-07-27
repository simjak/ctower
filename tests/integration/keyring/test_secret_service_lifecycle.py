"""Regression evidence for the Secret Service daemon process-group transition."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]
_LAUNCHER = Path(__file__).with_name("secret_service_launcher.py")
_PROCESS_HELPER = _ROOT / "tools/checks/owned_processes.py"
_LAUNCHER_OWNER_ENV = "CTOWER_TEST_LAUNCHER_OWNER"
_SERVICE_ROOT_ENV = "CTOWER_TEST_SERVICE_ROOT"


def test_launcher_waits_for_setsid_before_signalling_the_daemon_group(
    tmp_path: Path,
) -> None:
    shim = tmp_path / "setsid"
    trace = tmp_path / "setsid.trace"
    shim.write_text(_SETSID_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(tmp_path), environment["PATH"]))
    environment["CTOWER_TEST_SETSID_TRACE"] = str(trace)

    result = _run_launcher(environment)
    service_pid, inherited_pgid, service_root = _read_trace(trace)
    candidate_pids = (service_pid,)
    try:
        assert service_pid != inherited_pgid
        assert result.returncode == 0, result.stderr
        _assert_no_residue(
            service_root,
            candidate_pids=candidate_pids,
            candidate_session_ids=(service_pid,),
        )
    finally:
        _cleanup_exact_root(
            service_root,
            candidate_pids=candidate_pids,
            candidate_session_ids=(service_pid,),
        )


def test_cleanup_kills_owned_descendant_after_daemon_leader_exit(
    tmp_path: Path,
) -> None:
    daemon = tmp_path / "gnome-keyring-daemon"
    dbus_send = tmp_path / "dbus-send"
    trace = tmp_path / "daemon.trace"
    daemon.write_text(_FORKING_DAEMON_SHIM, encoding="utf-8")
    daemon.chmod(0o755)
    dbus_send.write_text(_SLOW_DBUS_SEND_SHIM, encoding="utf-8")
    dbus_send.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(tmp_path), environment["PATH"]))
    environment["CTOWER_TEST_DAEMON_TRACE"] = str(trace)

    result = _run_launcher(environment)
    leader_pid, child_pid, service_root = _read_daemon_trace(trace)
    candidate_pids = (leader_pid, child_pid)
    try:
        assert result.returncode != 0
        _assert_no_residue(
            service_root,
            candidate_pids=candidate_pids,
            candidate_session_ids=(leader_pid,),
        )
    finally:
        _cleanup_exact_root(
            service_root,
            candidate_pids=candidate_pids,
            candidate_session_ids=(leader_pid,),
        )


def _run_launcher(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    owner = f"lifecycle-{uuid.uuid4().hex}"
    environment = environment | {_LAUNCHER_OWNER_ENV: owner}
    process = subprocess.Popen(  # noqa: S603 - fixed repository launcher
        (sys.executable, str(_LAUNCHER), "-c", "pass"),
        cwd=_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_owned(
            _LAUNCHER_OWNER_ENV,
            owner,
            term_grace=0.25,
            kill_grace=1,
            candidate_pids=(process.pid,),
            candidate_session_ids=(process.pid,),
        )
        stdout, stderr = process.communicate(timeout=2)
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _read_trace(trace: Path) -> tuple[int, int, Path]:
    values = dict(
        field.split("=", maxsplit=1) for field in trace.read_text(encoding="utf-8").split()
    )
    return (
        int(values["pid"]),
        int(values["inherited_pgid"]),
        Path(values["service_root"]).resolve(),
    )


def _read_daemon_trace(trace: Path) -> tuple[int, int, Path]:
    values = dict(
        field.split("=", maxsplit=1) for field in trace.read_text(encoding="utf-8").split()
    )
    return (
        int(values["leader_pid"]),
        int(values["child_pid"]),
        Path(values["service_root"]).resolve(),
    )


def _assert_no_residue(
    service_root: Path,
    *,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> None:
    deadline = time.monotonic() + 2
    observation = _observe_root(
        service_root,
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
    )
    while time.monotonic() < deadline and observation.returncode == 1:
        time.sleep(0.02)
        observation = _observe_root(
            service_root,
            candidate_pids=candidate_pids,
            candidate_session_ids=candidate_session_ids,
        )
    assert not service_root.exists()
    assert observation.returncode == 0, observation.stderr


def _observe_root(
    service_root: Path,
    *,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> subprocess.CompletedProcess[str]:
    command = _process_helper_command(
        _SERVICE_ROOT_ENV,
        str(service_root),
        term_grace=0,
        kill_grace=0,
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
        observe_only=True,
    )
    return subprocess.run(  # noqa: S603 - fixed repository helper
        command,
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _cleanup_exact_root(
    service_root: Path,
    *,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> None:
    _terminate_owned(
        _SERVICE_ROOT_ENV,
        str(service_root),
        term_grace=0,
        kill_grace=1,
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
    )
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if service_root.parent == temporary_root and service_root.name.startswith("tmp."):
        shutil.rmtree(service_root, ignore_errors=True)


def _terminate_owned(
    environment_name: str,
    owner: str,
    *,
    term_grace: float,
    kill_grace: float,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
) -> None:
    command = _process_helper_command(
        environment_name,
        owner,
        term_grace=term_grace,
        kill_grace=kill_grace,
        candidate_pids=candidate_pids,
        candidate_session_ids=candidate_session_ids,
        observe_only=False,
    )
    subprocess.run(  # noqa: S603 - fixed repository helper
        command,
        cwd=_ROOT,
        check=False,
    )


def _process_helper_command(
    environment_name: str,
    owner: str,
    *,
    term_grace: float,
    kill_grace: float,
    candidate_pids: tuple[int, ...],
    candidate_session_ids: tuple[int, ...],
    observe_only: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(_PROCESS_HELPER),
        environment_name,
        owner,
        "--term-grace-seconds",
        str(term_grace),
        "--kill-grace-seconds",
        str(kill_grace),
    ]
    for candidate_pid in candidate_pids:
        command.extend(("--candidate-pid", str(candidate_pid)))
    for candidate_session_id in candidate_session_ids:
        command.extend(("--candidate-session-id", str(candidate_session_id)))
    if observe_only:
        command.append("--observe-only")
    return command


_SETSID_SHIM = """#!/usr/bin/python3
import os
import sys
import time
from pathlib import Path

trace = (
    f"pid={os.getpid()} inherited_pgid={os.getpgid(0)} "
    f"service_root={os.environ['CTOWER_TEST_SERVICE_ROOT']}\\n"
)
Path(os.environ["CTOWER_TEST_SETSID_TRACE"]).write_text(trace, encoding="utf-8")
time.sleep(0.25)
os.execv("/usr/bin/setsid", ("/usr/bin/setsid", *sys.argv[1:]))
"""

_FORKING_DAEMON_SHIM = """#!/usr/bin/python3
import os
import signal
import time
from pathlib import Path

child_pid = os.fork()
if child_pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        signal.pause()

trace = (
    f"leader_pid={os.getpid()} child_pid={child_pid} "
    f"service_root={os.environ['CTOWER_TEST_SERVICE_ROOT']}\\n"
)
Path(os.environ["CTOWER_TEST_DAEMON_TRACE"]).write_text(trace, encoding="utf-8")
time.sleep(0.15)
"""

_SLOW_DBUS_SEND_SHIM = """#!/usr/bin/python3
import time

time.sleep(0.5)
raise SystemExit(1)
"""
