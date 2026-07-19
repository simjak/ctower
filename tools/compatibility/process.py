from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import shutil
import signal
import subprocess
import sys
import sysconfig
import threading
import time
from pathlib import Path
from typing import IO, Literal, Protocol, cast

from .models_core import (
    CompatibilityError,
    HostIdentity,
    ProcessRequest,
    ProcessResult,
    PythonVersion,
    RuntimeDetails,
)

__all__ = ["ExecutionPort", "LocalExecutionPort", "ProbePort"]


class ExecutionPort(Protocol):
    """The one injectable public boundary for tools, host identity, and processes."""

    def resolve_tool(self, name: str) -> str | None: ...

    def host_identity(self) -> HostIdentity: ...

    def run(self, request: ProcessRequest) -> ProcessResult: ...


class ProbePort(ExecutionPort, Protocol):
    """Public adapter for runtime metadata used by the contained probe."""

    def runtime_details(self, expected_version: PythonVersion) -> RuntimeDetails: ...

    def distribution_version(self, name: str) -> str: ...


class LocalExecutionPort:
    """Real argv-only execution with deadlines, process groups, and bounded output."""

    def resolve_tool(self, name: str) -> str | None:
        return shutil.which(name)

    def host_identity(self) -> HostIdentity:
        system = platform.system()
        if system not in {"Darwin", "Linux"}:
            raise CompatibilityError(f"unsupported host system: {system}")
        try:
            return HostIdentity(
                system=cast("Literal['Darwin', 'Linux']", system),
                machine=platform.machine(),
            )
        except ValueError as error:
            raise CompatibilityError(f"unsupported host identity: {error}") from error

    def run(self, request: ProcessRequest) -> ProcessResult:
        return _run_bounded(request)

    def runtime_details(self, expected_version: PythonVersion) -> RuntimeDetails:
        version = platform.python_version()
        if version != expected_version:
            raise CompatibilityError(f"expected Python {expected_version}, observed {version}")
        implementation = platform.python_implementation()
        if implementation != "CPython":
            raise CompatibilityError(f"unsupported interpreter implementation: {implementation}")
        system = platform.system()
        if system not in {"Darwin", "Linux"}:
            raise CompatibilityError(f"unsupported interpreter system: {system}")
        if not _gil_enabled():
            raise CompatibilityError("free-threaded interpreter is forbidden")
        return RuntimeDetails(
            version=expected_version,
            implementation=cast("Literal['CPython']", implementation),
            free_threaded=False,
            gil_enabled=True,
            system=cast("Literal['Darwin', 'Linux']", system),
            platform=platform.platform(),
            machine=platform.machine(),
            soabi=cast("str", sysconfig.get_config_var("SOABI")),
            cache_tag=sys.implementation.cache_tag,
            py_gil_disabled=0,
            executable_sha256=_file_sha256(Path(sys.executable)),
        )

    def distribution_version(self, name: str) -> str:
        return importlib.metadata.version(name)


class _BoundedCapture:
    """Drain one pipe continuously while retaining only a bounded diagnostic tail."""

    def __init__(self, stream: IO[bytes], limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._tail = bytearray()
        self.exceeded = threading.Event()
        self._failure: OSError | None = None
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        try:
            while chunk := self._stream.read(min(self._limit, 65_536)):
                self._append(chunk)
        except OSError as error:
            self._failure = error

    def _append(self, chunk: bytes) -> None:
        if len(self._tail) + len(chunk) > self._limit:
            self.exceeded.set()
        if len(chunk) >= self._limit:
            self._tail[:] = chunk[-self._limit :]
            return
        overflow = max(0, len(self._tail) + len(chunk) - self._limit)
        if overflow:
            del self._tail[:overflow]
        self._tail.extend(chunk)

    def finish(self, timeout_seconds: float) -> tuple[str, bool]:
        self._thread.join(timeout_seconds)
        if self._thread.is_alive():
            self._stream.close()
            self._thread.join(timeout_seconds)
        if self._thread.is_alive():
            raise CompatibilityError("process output pipe remained open after group termination")
        if self._failure is not None:
            raise CompatibilityError(f"unable to drain process output: {self._failure}")
        return bytes(self._tail).decode(errors="replace"), self.exceeded.is_set()


def _run_bounded(request: ProcessRequest) -> ProcessResult:
    process = _start_process(request)
    if process.stdout is None or process.stderr is None:
        raise CompatibilityError("process output pipes were not created")
    stdout = _BoundedCapture(process.stdout, request.output_limit_bytes)
    stderr = _BoundedCapture(process.stderr, request.output_limit_bytes)
    failure, termination = _supervise_process(process, request, stdout, stderr)
    output = stdout.finish(request.terminate_grace_ms / 1000)
    error = stderr.finish(request.terminate_grace_ms / 1000)
    returncode = process.wait(timeout=request.terminate_grace_ms / 1000)
    return ProcessResult(
        argv=request.argv,
        returncode=returncode,
        stdout=output[0],
        stderr=error[0],
        timed_out=failure == "timeout",
        termination=termination,
        stdout_truncated=output[1],
        stderr_truncated=error[1],
        failure_reason=failure,
    )


def _start_process(request: ProcessRequest) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(  # noqa: S603 - absolute argv model; shell is never used.
            request.argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=request.environment_dict(),
            process_group=0,
        )
    except OSError as error:
        raise CompatibilityError(f"unable to start {request.operation}: {error}") from error


def _supervise_process(
    process: subprocess.Popen[bytes],
    request: ProcessRequest,
    stdout: _BoundedCapture,
    stderr: _BoundedCapture,
) -> tuple[
    Literal["output_limit", "surviving_descendants", "timeout"] | None,
    Literal["exited", "terminated", "killed"],
]:
    deadline = time.monotonic() + (request.timeout_ms / 1000)
    while True:
        if stdout.exceeded.is_set() or stderr.exceeded.is_set():
            return "output_limit", _terminate_group(process, request)
        if process.poll() is not None:
            if _group_exists(process):
                return "surviving_descendants", _terminate_group(process, request)
            return None, "exited"
        if time.monotonic() >= deadline:
            return "timeout", _terminate_group(process, request)
        time.sleep(0.005)


def _terminate_group(
    process: subprocess.Popen[bytes], request: ProcessRequest
) -> Literal["exited", "terminated", "killed"]:
    grace_seconds = request.terminate_grace_ms / 1000
    if process.poll() is not None and not _group_exists(process):
        return "exited"
    _signal_group(process, signal.SIGTERM)
    if _wait_for_empty_group(process, grace_seconds):
        return "terminated"
    _signal_group(process, signal.SIGKILL)
    if not _wait_for_empty_group(process, grace_seconds):
        raise CompatibilityError(f"process group {process.pid} survived SIGKILL")
    return "killed"


def _wait_for_empty_group(process: subprocess.Popen[bytes], timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        process.poll()
        if not _group_exists(process):
            return True
        time.sleep(0.005)
    process.poll()
    return not _group_exists(process)


def _signal_group(process: subprocess.Popen[bytes], requested_signal: signal.Signals) -> None:
    deadline = time.monotonic() + 0.05
    while True:
        try:
            os.killpg(process.pid, requested_signal)
        except ProcessLookupError:
            return
        except PermissionError as error:
            if process.poll() is not None:
                return
            if time.monotonic() < deadline:
                time.sleep(0.001)
                continue
            raise CompatibilityError(f"could not signal process group {process.pid}") from error
        else:
            return


def _group_exists(process: subprocess.Popen[bytes]) -> bool:
    deadline = time.monotonic() + 0.05
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError as error:
            # Darwin can briefly report EPERM while an exited group becomes reapable.
            if process.poll() is not None:
                return False
            if time.monotonic() < deadline:
                time.sleep(0.001)
                continue
            raise CompatibilityError(f"cannot inspect process group {process.pid}") from error
        else:
            return True


def _gil_enabled() -> bool:
    probe = getattr(sys, "_is_gil_enabled", None)
    if probe is not None:
        return bool(probe())
    return sysconfig.get_config_var("Py_GIL_DISABLED") in (None, 0)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
