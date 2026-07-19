from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import shutil
import signal
import sys
import sysconfig
import tempfile
import threading
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, cast

from .contract import (
    CompatibilityError,
    HostIdentity,
    ProcessRequest,
    ProcessResult,
    PythonVersion,
    RuntimeDetails,
)


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


class _Child:
    def __init__(self, process_id: int) -> None:
        self.process_id = process_id
        self.completed = threading.Event()
        self.raw_status: int | None = None
        self.waiter = threading.Thread(target=self._wait, daemon=True)
        self.waiter.start()

    def _wait(self) -> None:
        _, self.raw_status = os.waitpid(self.process_id, 0)
        self.completed.set()

    def wait(self, timeout_seconds: float) -> bool:
        return self.completed.wait(timeout_seconds)

    def returncode(self) -> int:
        if self.raw_status is None:
            raise CompatibilityError("process remained alive after bounded termination")
        return os.waitstatus_to_exitcode(self.raw_status)


def _run_bounded(request: ProcessRequest) -> ProcessResult:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child = _start_process(request, stdout.fileno(), stderr.fileno())
        timed_out, termination = _wait_for_process(child, request)
        output = _bounded_text(stdout, request.output_limit_bytes)
        error = _bounded_text(stderr, request.output_limit_bytes)
    return ProcessResult(
        argv=request.argv,
        returncode=child.returncode(),
        stdout=output[0],
        stderr=error[0],
        timed_out=timed_out,
        termination=termination,
        stdout_truncated=output[1],
        stderr_truncated=error[1],
    )


def _start_process(
    request: ProcessRequest, stdout_descriptor: int, stderr_descriptor: int
) -> _Child:
    null_input = os.open(os.devnull, os.O_RDONLY)
    actions = (
        (os.POSIX_SPAWN_DUP2, null_input, 0),
        (os.POSIX_SPAWN_DUP2, stdout_descriptor, 1),
        (os.POSIX_SPAWN_DUP2, stderr_descriptor, 2),
        (os.POSIX_SPAWN_CLOSE, null_input),
        (os.POSIX_SPAWN_CLOSE, stdout_descriptor),
        (os.POSIX_SPAWN_CLOSE, stderr_descriptor),
    )
    try:
        process_id = os.posix_spawn(
            request.argv[0],
            request.argv,
            request.environment_dict(),
            file_actions=actions,
            setpgroup=0,
        )
    except OSError as error:
        raise CompatibilityError(f"unable to start {request.operation}: {error}") from error
    finally:
        os.close(null_input)
    return _Child(process_id)


def _wait_for_process(
    child: _Child, request: ProcessRequest
) -> tuple[bool, Literal["exited", "terminated", "killed"]]:
    if child.wait(request.timeout_ms / 1000):
        return False, "exited"
    _signal_group(child.process_id, signal.SIGTERM)
    if child.wait(request.terminate_grace_ms / 1000):
        return True, "terminated"
    _signal_group(child.process_id, signal.SIGKILL)
    if not child.wait(request.terminate_grace_ms / 1000):
        raise CompatibilityError("timed-out process group survived SIGKILL")
    return True, "killed"


def _signal_group(process_id: int, requested_signal: signal.Signals) -> None:
    try:
        os.killpg(process_id, requested_signal)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise CompatibilityError(
            f"could not signal timed-out process group {process_id}"
        ) from error


def _bounded_text(stream: BinaryIO, limit: int) -> tuple[str, bool]:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    truncated = size > limit
    stream.seek(max(0, size - limit))
    raw = stream.read()
    return raw.decode(errors="replace"), truncated


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
