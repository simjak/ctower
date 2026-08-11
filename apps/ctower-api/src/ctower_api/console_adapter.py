"""Registered read-only tmux/log Adapter for Console Phase 1."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import BinaryIO
from uuid import UUID

from ctower_kernel.console import (
    ConsoleBackendObservation,
    ConsoleOutputBatch,
    ConsoleSessionRef,
)
from ctower_kernel.record import RecordProblem
from tools.process_execution import run

__all__ = ["ConsoleBackendRegistration", "TmuxConsoleAdapter"]

type _CommandRunner = Callable[[tuple[str, ...]], CompletedProcess[str]]
type _RegistrationReader = Callable[[str], ConsoleBackendRegistration | None]
_INCARNATION_PARTS = 2


@dataclass(frozen=True, slots=True)
class ConsoleBackendRegistration:
    """One strict current-registry result for an exact runtime backend."""

    opaque_backend_ref: str
    tmux_target: str
    output_log: Path
    runtime_attempt_id: UUID
    runner_id: str
    runner_epoch: int
    output_device: int
    output_inode: int

    def __post_init__(self) -> None:
        _validate_backend_registration_identity(self)
        _validate_backend_registration_runtime(self)


def _validate_backend_registration_identity(registration: ConsoleBackendRegistration) -> None:
    if (
        not isinstance(registration.opaque_backend_ref, str)
        or not isinstance(registration.tmux_target, str)
        or not registration.opaque_backend_ref
        or not registration.tmux_target
    ):
        raise ValueError("console backend identity cannot be empty")
    if not isinstance(registration.output_log, Path):
        raise TypeError("console output log must be a path")
    if not registration.output_log.is_absolute():
        raise ValueError("console output log must be an absolute path")
    _validate_registered_log_identity(registration)


def _validate_registered_log_identity(registration: ConsoleBackendRegistration) -> None:
    if (
        not isinstance(registration.output_device, int)
        or isinstance(registration.output_device, bool)
        or registration.output_device < 0
    ):
        raise ValueError("console output log device cannot be negative")
    if (
        not isinstance(registration.output_inode, int)
        or isinstance(registration.output_inode, bool)
        or registration.output_inode < 1
    ):
        raise ValueError("console output log inode must be positive")


def _validate_backend_registration_runtime(registration: ConsoleBackendRegistration) -> None:
    if not isinstance(registration.runtime_attempt_id, UUID):
        raise TypeError("console runtime attempt must be a UUID")
    if not isinstance(registration.runner_id, str) or not registration.runner_id:
        raise ValueError("console runner identity cannot be empty")
    if (
        not isinstance(registration.runner_epoch, int)
        or isinstance(registration.runner_epoch, bool)
        or registration.runner_epoch < 1
    ):
        raise ValueError("console backend runner epoch must be positive")


class TmuxConsoleAdapter:
    """Reach only registered tmux targets and their already-captured raw logs."""

    def __init__(
        self,
        *,
        tmux_binary: str,
        socket_name: str,
        allowed_log_root: Path,
        registration_reader: _RegistrationReader,
        command_runner: _CommandRunner | None = None,
    ) -> None:
        if not tmux_binary or not socket_name or not callable(registration_reader):
            raise ValueError("tmux binary and socket name must be explicit")
        self._tmux_binary = tmux_binary
        self._socket_name = socket_name
        self._allowed_log_root = allowed_log_root.resolve(strict=True)
        self._command_runner = command_runner or _run_command
        self._registration_reader = registration_reader

    def inspect(self, session_ref: ConsoleSessionRef) -> ConsoleBackendObservation | RecordProblem:
        registration = self._registration(session_ref)
        if isinstance(registration, RecordProblem):
            return registration
        return self._observe(session_ref, registration)

    def _observe(
        self,
        session_ref: ConsoleSessionRef,
        registration: ConsoleBackendRegistration,
    ) -> ConsoleBackendObservation | RecordProblem:
        project = self._invoke("show-options", "-t", registration.tmux_target, "-v", "@project")
        if isinstance(project, RecordProblem):
            return project
        project_key = project.strip()
        if project_key != session_ref.project_key:
            return _problem(
                "console-project-fence-mismatch",
                "The live tmux @project fact does not match the exact session reference.",
            )
        incarnation = self._invoke(
            "display-message",
            "-p",
            "-t",
            registration.tmux_target,
            "#{session_id}\t#{session_created}",
        )
        if isinstance(incarnation, RecordProblem):
            return incarnation
        parts = incarnation.strip().split("\t")
        if len(parts) != _INCARNATION_PARTS or not all(parts):
            return _problem(
                "console-adapter-malformed",
                "The tmux Adapter returned no provable session incarnation.",
            )
        return ConsoleBackendObservation(
            project_key=project_key,
            runtime_attempt_id=registration.runtime_attempt_id,
            runner_id=registration.runner_id,
            runner_epoch=registration.runner_epoch,
            opaque_backend_ref=registration.opaque_backend_ref,
            backend_incarnation=":".join(parts),
        )

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch | RecordProblem:
        """Read an exact byte range from a registered pipe-pane log."""

        if after_cursor < 0 or not 1 <= maximum_bytes <= 1024 * 1024:
            return _problem("console-cursor-invalid", "The requested output range is invalid.")
        registration = self._registration(session_ref)
        if isinstance(registration, RecordProblem):
            return registration
        before = self._observe(session_ref, registration)
        if isinstance(before, RecordProblem) or not _observation_matches(session_ref, before):
            return _fenced_observation(before)
        snapshot = self._read_snapshot(registration, after_cursor, maximum_bytes)
        if not isinstance(snapshot, tuple):
            return snapshot
        payload, source_cursor = snapshot
        fence = self._post_read_fence(session_ref, registration)
        return fence or ConsoleOutputBatch(payload=payload, source_cursor=source_cursor)

    def _read_snapshot(
        self,
        registration: ConsoleBackendRegistration,
        after_cursor: int,
        maximum_bytes: int,
    ) -> tuple[bytes, int] | ConsoleOutputBatch | RecordProblem:
        try:
            stream = _open_log_beneath(self._allowed_log_root, registration.output_log)
        except OSError:
            return _problem("console-output-unavailable", "The registered output log is absent.")
        with stream:
            identity = os.fstat(stream.fileno())
            if (identity.st_dev, identity.st_ino) != (
                registration.output_device,
                registration.output_inode,
            ):
                return _problem(
                    "console-runtime-attempt-fenced",
                    "The registered output log was replaced.",
                )
            size = identity.st_size
            if after_cursor > size:
                return ConsoleOutputBatch(
                    payload=b"",
                    source_cursor=size,
                    gap=True,
                    gap_reason="source-truncated",
                )
            stream.seek(after_cursor)
            payload = stream.read(maximum_bytes)
        return payload, after_cursor + len(payload)

    def _post_read_fence(
        self,
        session_ref: ConsoleSessionRef,
        registration: ConsoleBackendRegistration,
    ) -> RecordProblem | None:
        current = self._registration(session_ref)
        if isinstance(current, RecordProblem):
            return current
        after = self._observe(session_ref, current)
        if (
            current != registration
            or isinstance(after, RecordProblem)
            or not _observation_matches(session_ref, after)
        ):
            return _fenced_observation(after)
        return None

    def _registration(
        self, session_ref: ConsoleSessionRef
    ) -> ConsoleBackendRegistration | RecordProblem:
        if session_ref.adapter_key != "tmux-v1":
            return _problem(
                "console-adapter-unregistered", "The requested Adapter kind is not registered."
            )
        registration = self._registration_reader(session_ref.opaque_backend_ref)
        if registration is None:
            return _problem(
                "console-adapter-unregistered", "The requested backend is not registered."
            )
        if (
            not isinstance(registration, ConsoleBackendRegistration)
            or registration.opaque_backend_ref != session_ref.opaque_backend_ref
        ):
            return _problem(
                "console-adapter-malformed",
                "The current backend registry returned a mismatched registration.",
            )
        if _relative_log_path(self._allowed_log_root, registration.output_log) is None:
            return _problem(
                "console-adapter-unregistered",
                "The registered output log is outside the allowlisted root.",
            )
        return registration

    def _invoke(self, *arguments: str) -> str | RecordProblem:
        command = (self._tmux_binary, "-L", self._socket_name, *arguments)
        completed = self._command_runner(command)
        if completed.returncode != 0:
            return _problem("console-backend-unavailable", "The registered tmux target is absent.")
        return completed.stdout


def _run_command(command: tuple[str, ...]) -> CompletedProcess[str]:
    return run(
        command,
        timeout_seconds=2,
        check=False,
        capture_output=True,
    )


def _problem(code: str, detail: str) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=403, title="Console backend refused")


def _observation_matches(
    session_ref: ConsoleSessionRef, observation: ConsoleBackendObservation
) -> bool:
    return (
        observation.project_key == session_ref.project_key
        and observation.runtime_attempt_id == session_ref.runtime_attempt_id
        and observation.runner_id == session_ref.runner_id
        and observation.runner_epoch == session_ref.runner_epoch
        and observation.opaque_backend_ref == session_ref.opaque_backend_ref
        and observation.backend_incarnation == session_ref.backend_incarnation
    )


def _fenced_observation(
    observation: ConsoleBackendObservation | RecordProblem,
) -> RecordProblem:
    if isinstance(observation, RecordProblem):
        return observation
    return _problem(
        "console-runtime-attempt-fenced",
        "The registered runtime changed across the bounded output read.",
    )


def _relative_log_path(root: Path, output_log: Path) -> Path | None:
    try:
        relative = output_log.relative_to(root)
    except ValueError:
        return None
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    return relative


def _open_log_beneath(root: Path, output_log: Path) -> BinaryIO:
    relative = _relative_log_path(root, output_log)
    if relative is None:
        raise FileNotFoundError("registered log is outside its root")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    directory_fd = root_fd
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            if directory_fd != root_fd:
                os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(relative.parts[-1], file_flags, dir_fd=directory_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            os.close(file_fd)
            raise FileNotFoundError("registered output is not a regular file")
        return os.fdopen(file_fd, "rb", closefd=True)
    finally:
        if directory_fd != root_fd:
            os.close(directory_fd)
        os.close(root_fd)
