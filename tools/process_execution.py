"""Bounded process execution with owned-descendant termination."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Sequence
from contextlib import suppress

__all__ = ["ProcessTimeoutError", "pipeline", "run"]

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
    inherited_descriptors: Sequence[int] = (),
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
        pass_fds=tuple(inherited_descriptors),
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _terminate_process_group(process)
        raise ProcessTimeoutError(arguments, timeout_seconds) from error
    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    return _checked(result, check=check)


def pipeline(
    producer: Sequence[str],
    consumer: Sequence[str],
    *,
    timeout_seconds: float,
    producer_descriptors: Sequence[int] = (),
    consumer_descriptors: Sequence[int] = (),
) -> None:
    """Join two bounded processes by one anonymous pipe under one shared deadline.

    The payload never reaches an argument vector, an environment variable, or a
    filesystem path, and inherited descriptors carry no name a third process can open.
    """

    _validate_deadline(timeout_seconds)
    read_end, write_end = os.pipe()
    try:
        first = _spawn(producer, subprocess.DEVNULL, write_end, producer_descriptors)
        try:
            second = _spawn(consumer, read_end, subprocess.DEVNULL, consumer_descriptors)
        except BaseException:
            _terminate_process_group(first)
            raise
    finally:
        os.close(read_end)
        os.close(write_end)
    _await_pipeline(((first, producer), (second, consumer)), timeout_seconds)


def _spawn(
    arguments: Sequence[str],
    stdin: int,
    stdout: int,
    descriptors: Sequence[int],
) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603 - this is the single bounded process boundary
        tuple(arguments),
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
        pass_fds=tuple(descriptors),
    )


def _await_pipeline(
    stages: tuple[tuple[subprocess.Popen[str], Sequence[str]], ...],
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    results: list[subprocess.CompletedProcess[str]] = []
    for process, arguments in stages:
        try:
            _, stderr = process.communicate(timeout=max(deadline - time.monotonic(), 0.0))
        except subprocess.TimeoutExpired as error:
            for stage, _stage_arguments in stages:
                _terminate_process_group(stage)
            raise ProcessTimeoutError(arguments, timeout_seconds) from error
        results.append(subprocess.CompletedProcess(process.args, process.returncode, None, stderr))
    for result in results:
        _checked(result, check=True)


def _validate_deadline(timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        raise ValueError("process timeout must be positive")


def _validate_options(
    timeout_seconds: float,
    *,
    capture_output: bool,
    discard_output: bool,
) -> None:
    _validate_deadline(timeout_seconds)
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
