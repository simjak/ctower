"""Regression evidence for the Secret Service daemon process-group transition."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]
_LAUNCHER = Path(__file__).with_name("secret_service_launcher.py")


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
    try:
        assert service_pid != inherited_pgid
        assert result.returncode == 0, result.stderr
        _assert_no_residue(service_root)
    finally:
        _cleanup_exact_root(service_root)


def _run_launcher(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
        os.killpg(process.pid, signal.SIGKILL)
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


def _assert_no_residue(service_root: Path) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and _processes_for_root(service_root):
        time.sleep(0.02)
    assert not service_root.exists()
    assert not _processes_for_root(service_root)


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


def _cleanup_exact_root(service_root: Path) -> None:
    for pid in _processes_for_root(service_root):
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if service_root.parent == temporary_root and service_root.name.startswith("tmp."):
        shutil.rmtree(service_root, ignore_errors=True)


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
