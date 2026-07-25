"""Non-skipped Linux Secret Service creation, process reload, and absence evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

import keyring

from ctowerctl.spool._keyring import create_master_key

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXIT_LOCAL_FAILURE = 74
_SERVICE = "ctower-spool-v1"
_LAUNCHER = ROOT / "tests/integration/keyring/secret_service_launcher.py"
_STAGE_PREFIX = "[ctower-secret-service]"
_MIN_SAFE_ROOT_PARTS = 3


def test_secret_service_creates_and_loads_key_across_processes() -> None:
    _stage("proof-backend-selection")
    _assert_isolated_service()
    backend = keyring.get_keyring()
    identity = (backend.__class__.__module__, backend.__class__.__name__)
    assert identity == ("keyring.backends.SecretService", "Keyring")
    assert backend.priority > 0

    spool_uuid = uuid4()
    created = False
    try:
        _stage("proof-create")
        expected_digest = hashlib.sha256(create_master_key(spool_uuid)).hexdigest()
        created = True
        _stage("proof-reload-with-session-bus")
        loaded = _keyring_child(spool_uuid, expected_digest, with_session_bus=True)
        _stage("proof-reload-without-session-bus")
        absent = _keyring_child(spool_uuid, expected_digest, with_session_bus=False)

        assert loaded.returncode == 0, loaded.stderr
        assert absent.returncode == EXIT_LOCAL_FAILURE, absent.stderr
        assert loaded.stdout == absent.stdout == ""
    finally:
        if created:
            _stage("proof-delete")
            keyring.delete_password(_SERVICE, str(spool_uuid))
    _stage("proof-final-absence")
    assert backend.get_password(_SERVICE, str(spool_uuid)) is None


def test_secret_service_launcher_waits_for_verified_daemon_pgid_before_group_signal(
    tmp_path: Path,
) -> None:
    environment, trace_path = _setsid_probe_environment(tmp_path, mode="delay")
    result = asyncio.run(_run_launcher(environment, "real", deadline_seconds=15.0))
    service_root = _service_root_from_stderr(result.stderr)
    trace: _SetsidTrace | None = None
    try:
        trace = _read_setsid_trace(trace_path)
        assert not result.timed_out, result.stderr
        assert trace.inherited_pgid != trace.pid
        assert trace.service_root == service_root
        assert result.returncode == 0, result.stderr
        assert "stage=daemon-pgid-verified" in result.stderr
        assert "stage=test-command-complete status=0" in result.stderr
        _assert_no_exact_residue(service_root, (trace.pid,))
    finally:
        recorded_pids = () if trace is None else (trace.pid,)
        _cleanup_exact_probe(service_root, recorded_pids)


def test_secret_service_launcher_never_signals_an_unverified_inherited_group(
    tmp_path: Path,
) -> None:
    environment, trace_path = _setsid_probe_environment(tmp_path, mode="never")
    result = asyncio.run(_run_launcher(environment, "controlled-failure", deadline_seconds=12.0))
    service_root = _service_root_from_stderr(result.stderr)
    trace: _SetsidTrace | None = None
    try:
        trace = _read_setsid_trace(trace_path)
        assert trace.sentinel_pid is not None
        assert not result.timed_out, result.stderr
        assert trace.inherited_pgid != trace.pid
        assert trace.service_root == service_root
        assert result.returncode == 1, result.stderr
        assert "stage=daemon-pgid-verification-failed reason=timeout" in result.stderr
        assert f"stage=cleanup-term target=pid:{trace.pid}" in result.stderr
        assert _pid_exists(trace.sentinel_pid)
        _assert_no_exact_residue(service_root, (trace.pid,))
    finally:
        recorded_pids: tuple[int, ...] = ()
        if trace is not None and trace.sentinel_pid is not None:
            recorded_pids = (trace.pid, trace.sentinel_pid)
        _cleanup_exact_probe(service_root, recorded_pids)


def test_secret_service_suite_timeout_removes_daemon_and_service_root(
    tmp_path: Path,
) -> None:
    child_trace = tmp_path / "timeout-children"
    environment = os.environ.copy()
    environment["CTOWER_TEST_TIMEOUT_CHILD_TRACE"] = str(child_trace)
    result, escalated = asyncio.run(_terminate_like_expected_suite(environment))
    service_root = _service_root_from_stderr(result.stderr)
    child_pids: tuple[int, ...] = ()
    try:
        child_pids = _read_pid_trace(child_trace)
        assert result.timed_out
        assert not escalated, result.stderr
        assert result.returncode != 0
        assert "stage=cleanup-term" in result.stderr
        assert "stage=cleanup-complete command_status=143" in result.stderr
        _assert_no_exact_residue(service_root, child_pids)
    finally:
        _cleanup_exact_probe(service_root, child_pids)


def _stage(name: str) -> None:
    print(f"{_STAGE_PREFIX} stage={name}", file=sys.stderr, flush=True)


def _assert_isolated_service() -> None:
    service_root = Path(os.environ["CTOWER_TEST_SERVICE_ROOT"]).resolve()
    home = Path.home().resolve()
    runtime = Path(os.environ["XDG_RUNTIME_DIR"]).resolve()
    assert home.is_relative_to(service_root)
    assert runtime.is_relative_to(service_root)
    assert home != Path(os.environ["CTOWER_TEST_HOST_HOME"]).resolve()
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] != os.environ["CTOWER_TEST_HOST_BUS"]


def _keyring_child(
    spool_uuid: object,
    expected_digest: str,
    *,
    with_session_bus: bool,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / relative)
        for relative in (
            "apps/ctowerctl/src",
            "generated/python",
        )
    )
    if not with_session_bus:
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        environment.pop("GNOME_KEYRING_CONTROL", None)
    environment["CTOWER_KEYRING_CHILD"] = _child_command(spool_uuid, expected_digest)
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_KEYRING_CHILD')); "
            "os.execv(command[0], command)",
        ),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _child_command(spool_uuid: object, expected_digest: str) -> str:
    return json.dumps((sys.executable, "-c", _CHILD, str(spool_uuid), expected_digest))


@dataclass(frozen=True)
class _LaunchResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True)
class _SetsidTrace:
    pid: int
    inherited_pgid: int
    service_root: Path
    sentinel_pid: int | None


def _setsid_probe_environment(tmp_path: Path, *, mode: str) -> tuple[dict[str, str], Path]:
    shim_directory = tmp_path / "shim"
    shim_directory.mkdir()
    shim = shim_directory / "setsid"
    shim.write_text(_SETSID_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    trace_path = tmp_path / "setsid-trace"
    environment = os.environ.copy()
    environment["PATH"] = f"{shim_directory}{os.pathsep}{environment['PATH']}"
    environment["CTOWER_TEST_SETSID_MODE"] = mode
    environment["CTOWER_TEST_SETSID_TRACE"] = str(trace_path)
    return environment, trace_path


async def _start_launcher(
    environment: dict[str, str],
    probe: Literal["real", "controlled-failure", "blocking"],
) -> asyncio.subprocess.Process:
    if probe == "real":
        python_source = _REAL_SERVICE_PROBE
    elif probe == "controlled-failure":
        python_source = _CONTROLLED_FAILURE_PROBE
    else:
        python_source = _BLOCKING_PROBE
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(_LAUNCHER),
        "-c",
        python_source,
        cwd=ROOT,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )


async def _run_launcher(
    environment: dict[str, str],
    probe: Literal["real", "controlled-failure", "blocking"],
    *,
    deadline_seconds: float,
) -> _LaunchResult:
    process = await _start_launcher(environment, probe)
    communication = asyncio.create_task(process.communicate())
    finished, _ = await asyncio.wait((communication,), timeout=deadline_seconds)
    timed_out = not finished
    if timed_out:
        _signal_process_group(process.pid, signal.SIGKILL)
    stdout, stderr = await asyncio.wait_for(communication, timeout=2.0)
    assert process.returncode is not None
    return _LaunchResult(
        process.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        timed_out,
    )


async def _terminate_like_expected_suite(
    environment: dict[str, str],
) -> tuple[_LaunchResult, bool]:
    process = await _start_launcher(environment, "blocking")
    communication = asyncio.create_task(process.communicate())
    finished, _ = await asyncio.wait((communication,), timeout=1.0)
    if finished:
        return _completed_launch_result(process, communication, timed_out=False), False

    _signal_process_group(process.pid, signal.SIGTERM)
    escalated = False
    finished, _ = await asyncio.wait((communication,), timeout=0.25)
    if not finished:
        escalated = True
        _signal_process_group(process.pid, signal.SIGKILL)
    await asyncio.wait_for(communication, timeout=2.0)
    return _completed_launch_result(process, communication, timed_out=True), escalated


def _completed_launch_result(
    process: asyncio.subprocess.Process,
    communication: asyncio.Task[tuple[bytes, bytes]],
    *,
    timed_out: bool,
) -> _LaunchResult:
    stdout, stderr = communication.result()
    assert process.returncode is not None
    return _LaunchResult(
        process.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
        timed_out,
    )


def _signal_process_group(leader_pid: int, sent_signal: signal.Signals) -> None:
    with suppress(ProcessLookupError):
        os.killpg(leader_pid, sent_signal)


def _service_root_from_stderr(stderr: str) -> Path:
    marker = "stage=session-bus-start root="
    roots = [
        Path(line.split(marker, maxsplit=1)[1]).resolve()
        for line in stderr.splitlines()
        if marker in line
    ]
    assert len(roots) == 1, stderr
    root = roots[0]
    assert _is_safe_service_root(root)
    return root


def _read_setsid_trace(trace_path: Path) -> _SetsidTrace:
    values: dict[str, str] = {}
    for field in trace_path.read_text(encoding="utf-8").strip().split():
        name, value = field.split("=", maxsplit=1)
        values[name] = value
    sentinel_pid = int(values["sentinel_pid"])
    return _SetsidTrace(
        pid=int(values["pid"]),
        inherited_pgid=int(values["inherited_pgid"]),
        service_root=Path(values["service_root"]).resolve(),
        sentinel_pid=sentinel_pid or None,
    )


def _read_pid_trace(trace_path: Path) -> tuple[int, ...]:
    return tuple(int(value) for value in trace_path.read_text(encoding="utf-8").split())


def _assert_no_exact_residue(service_root: Path, recorded_pids: tuple[int, ...]) -> None:
    deadline = time.monotonic() + 2.0
    remaining_pids = set(recorded_pids)
    root_processes = _processes_for_root(service_root)
    while time.monotonic() < deadline and (remaining_pids or root_processes):
        time.sleep(0.02)
        remaining_pids = {pid for pid in remaining_pids if _pid_exists(pid)}
        root_processes = _processes_for_root(service_root)
    assert not service_root.exists()
    assert not remaining_pids
    assert not root_processes


def _processes_for_root(service_root: Path) -> set[int]:
    root_entry = os.fsencode(f"CTOWER_TEST_SERVICE_ROOT={service_root}")
    matches: set[int] = set()
    for process_directory in Path("/proc").iterdir():
        if not process_directory.name.isdigit():
            continue
        try:
            environment = (process_directory / "environ").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if root_entry in environment:
            matches.add(int(process_directory.name))
    return matches


def _pid_exists(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def _cleanup_exact_probe(service_root: Path, recorded_pids: tuple[int, ...]) -> None:
    for pid in set(recorded_pids) | _processes_for_root(service_root):
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    if _is_safe_service_root(service_root):
        shutil.rmtree(service_root, ignore_errors=True)


def _is_safe_service_root(service_root: Path) -> bool:
    return (
        service_root.is_absolute()
        and len(service_root.parts) >= _MIN_SAFE_ROOT_PARTS
        and service_root.name.startswith("tmp.")
    )


_CHILD = """
import hashlib
import sys
from uuid import UUID
from ctowerctl.spool._keyring import KeyringError, load_master_key
try:
    digest = hashlib.sha256(load_master_key(UUID(sys.argv[1]))).hexdigest()
except KeyringError:
    raise SystemExit(74)
raise SystemExit(0 if digest == sys.argv[2] else 1)
"""

_REAL_SERVICE_PROBE = """
import keyring
from uuid import uuid4
service = "ctower-pgid-probe"
username = str(uuid4())
keyring.set_password(service, username, "verified")
try:
    assert keyring.get_password(service, username) == "verified"
finally:
    keyring.delete_password(service, username)
assert keyring.get_password(service, username) is None
"""

_CONTROLLED_FAILURE_PROBE = "raise SystemExit(97)"

_BLOCKING_PROBE = """
import os
import subprocess
import sys
import time
from pathlib import Path
child = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(60)"))
Path(os.environ["CTOWER_TEST_TIMEOUT_CHILD_TRACE"]).write_text(
    f"{os.getpid()} {child.pid}\\n",
    encoding="utf-8",
)
time.sleep(60)
"""

_SETSID_SHIM = """#!/usr/bin/python3
import os
import subprocess
import sys
import time
from pathlib import Path

mode = os.environ["CTOWER_TEST_SETSID_MODE"]
sentinel_pid = 0
if mode == "never":
    sentinel_environment = os.environ.copy()
    host_home = sentinel_environment["CTOWER_TEST_HOST_HOME"]
    for name in tuple(sentinel_environment):
        if name.startswith("CTOWER_TEST_"):
            sentinel_environment.pop(name)
    for name in ("DBUS_SESSION_BUS_ADDRESS", "GNOME_KEYRING_CONTROL", "XDG_RUNTIME_DIR"):
        sentinel_environment.pop(name, None)
    sentinel_environment["HOME"] = host_home
    sentinel = subprocess.Popen(
        ("/usr/bin/python3", "-c", "import time; time.sleep(60)"),
        env=sentinel_environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    sentinel_pid = sentinel.pid
trace = (
    f"pid={os.getpid()} inherited_pgid={os.getpgid(0)} "
    f"service_root={os.environ['CTOWER_TEST_SERVICE_ROOT']} "
    f"sentinel_pid={sentinel_pid}\\n"
)
Path(os.environ["CTOWER_TEST_SETSID_TRACE"]).write_text(trace, encoding="utf-8")
time.sleep(10.0 if mode == "never" else 0.25)
os.execv("/usr/bin/setsid", ("/usr/bin/setsid", *sys.argv[1:]))
"""
