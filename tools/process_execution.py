"""Bounded process execution with owned-descendant termination."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Sequence
from contextlib import suppress

__all__ = ["ProcessTimeoutError", "run"]

_TERMINATION_GRACE_SECONDS = 1.0


class ProcessTimeoutError(RuntimeError):
    """A bounded process and its owned descendants exceeded their deadline."""

    def __init__(self, arguments: Sequence[str], timeout_seconds: float) -> None:
        self.arguments = tuple(arguments)
        self.timeout_seconds = timeout_seconds
        super().__init__(f"process exceeded its {timeout_seconds:g} second deadline")


def run(
    arguments: Sequence[str],
    *,
    timeout_seconds: float,
    check: bool,
    input_text: str | None = None,
    capture_output: bool = False,
    discard_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one process group and terminate all owned descendants on timeout."""

    _validate_options(
        timeout_seconds,
        capture_output=capture_output,
        discard_output=discard_output,
    )
    output = _output_target(
        capture_output=capture_output,
        discard_output=discard_output,
    )
    process = subprocess.Popen(  # noqa: S603 - this is the single bounded process boundary
        tuple(arguments),
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=output,
        stderr=output,
        start_new_session=True,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _terminate_process_group(process)
        raise ProcessTimeoutError(arguments, timeout_seconds) from error
    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    return _checked(result, check=check)


def _validate_options(
    timeout_seconds: float,
    *,
    capture_output: bool,
    discard_output: bool,
) -> None:
    if timeout_seconds <= 0:
        raise ValueError("process timeout must be positive")
    if capture_output and discard_output:
        raise ValueError("process output cannot be captured and discarded together")


def _output_target(*, capture_output: bool, discard_output: bool) -> int | None:
    if capture_output:
        return subprocess.PIPE
    if discard_output:
        return subprocess.DEVNULL
    return None


def _checked(
    result: subprocess.CompletedProcess[str],
    *,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    if check:
        result.check_returncode()
    return result


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.communicate()
        return
    try:
        process.communicate(timeout=_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
