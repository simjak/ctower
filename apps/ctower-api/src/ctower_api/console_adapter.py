"""Registered read-only tmux/log Adapter for Console Phase 1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
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
_INCARNATION_PARTS = 2


@dataclass(frozen=True, slots=True)
class ConsoleBackendRegistration:
    """Deploy-time mapping from an opaque ref to one exact runtime backend."""

    opaque_backend_ref: str
    tmux_target: str
    output_log: Path
    runtime_attempt_id: UUID
    runner_id: str
    runner_epoch: int

    def __post_init__(self) -> None:
        if not self.opaque_backend_ref or not self.tmux_target:
            raise ValueError("console backend identity cannot be empty")
        if self.runner_epoch < 1:
            raise ValueError("console backend runner epoch must be positive")


class TmuxConsoleAdapter:
    """Reach only registered tmux targets and their already-captured raw logs."""

    def __init__(
        self,
        *,
        tmux_binary: str,
        socket_name: str,
        allowed_log_root: Path,
        registrations: tuple[ConsoleBackendRegistration, ...],
        command_runner: _CommandRunner | None = None,
    ) -> None:
        if not tmux_binary or not socket_name:
            raise ValueError("tmux binary and socket name must be explicit")
        self._tmux_binary = tmux_binary
        self._socket_name = socket_name
        self._allowed_log_root = allowed_log_root.resolve(strict=True)
        self._command_runner = command_runner or _run_command
        self._registrations: dict[str, ConsoleBackendRegistration] = {}
        for registration in registrations:
            resolved = registration.output_log.resolve(strict=False)
            if not resolved.is_relative_to(self._allowed_log_root):
                raise ValueError("console output log is outside the allowlisted root")
            if registration.opaque_backend_ref in self._registrations:
                raise ValueError("console backend references must be unique")
            self._registrations[registration.opaque_backend_ref] = registration

    def inspect(self, session_ref: ConsoleSessionRef) -> ConsoleBackendObservation | RecordProblem:
        registration = self._registration(session_ref)
        if isinstance(registration, RecordProblem):
            return registration
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

        registration = self._registration(session_ref)
        if isinstance(registration, RecordProblem):
            return registration
        if after_cursor < 0 or not 1 <= maximum_bytes <= 1024 * 1024:
            return _problem("console-cursor-invalid", "The requested output range is invalid.")
        path = registration.output_log.resolve(strict=False)
        if not path.is_relative_to(self._allowed_log_root) or not path.is_file():
            return _problem("console-output-unavailable", "The registered output log is absent.")
        size = path.stat().st_size
        if after_cursor > size:
            return ConsoleOutputBatch(
                payload=b"",
                source_cursor=size,
                gap=True,
                gap_reason="source-truncated",
            )
        with path.open("rb") as stream:
            stream.seek(after_cursor)
            payload = stream.read(maximum_bytes)
        return ConsoleOutputBatch(payload=payload, source_cursor=after_cursor + len(payload))

    def _registration(
        self, session_ref: ConsoleSessionRef
    ) -> ConsoleBackendRegistration | RecordProblem:
        if session_ref.adapter_key != "tmux-v1":
            return _problem(
                "console-adapter-unregistered", "The requested Adapter kind is not registered."
            )
        registration = self._registrations.get(session_ref.opaque_backend_ref)
        if registration is None:
            return _problem(
                "console-adapter-unregistered", "The requested backend is not registered."
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
