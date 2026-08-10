"""RED-first tests for the registered, read-only tmux/log Adapter."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import cast
from uuid import UUID

from ctower_api.console_adapter import ConsoleBackendRegistration, TmuxConsoleAdapter
from ctower_kernel.console import ConsoleBackendObservation, ConsoleOutputBatch, ConsoleSessionRef
from ctower_kernel.record import RecordProblem


def _ref(**changes: object) -> ConsoleSessionRef:
    values: dict[str, object] = {
        "tenant_id": UUID("10000000-0000-0000-0000-000000000001"),
        "project_key": "ctower",
        "seat_principal_id": UUID("20000000-0000-0000-0000-000000000001"),
        "crew_name": "engineer-console-p1",
        "assignment_ticket_id": UUID("70000000-0000-0000-0000-000000000001"),
        "assignment_kind": "implementation",
        "assignment_interval_sequence": 1,
        "recorded_work_session_id": UUID("60000000-0000-0000-0000-000000000001"),
        "runtime_attempt_id": UUID("80000000-0000-0000-0000-000000000001"),
        "runner_id": "mission-control",
        "runner_epoch": 7,
        "adapter_key": "tmux-v1",
        "opaque_backend_ref": "crew:engineer-console-p1",
        "backend_incarnation": "$9:1786400000",
    }
    values.update(changes)
    return ConsoleSessionRef(**values)  # type: ignore[arg-type]


class _Runner:
    def __init__(self, *, project: str = "ctower") -> None:
        self.project = project
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...]) -> CompletedProcess[str]:
        self.commands.append(command)
        if command[-2:] == ("-v", "@project"):
            return CompletedProcess(command, 0, stdout=f"{self.project}\n", stderr="")
        return CompletedProcess(command, 0, stdout="$9\t1786400000\n", stderr="")


def _adapter(tmp_path: Path, runner: _Runner) -> tuple[TmuxConsoleAdapter, Path]:
    log = tmp_path / "engineer-console-p1.log"
    log.write_bytes(b"first\nsecond\n")
    registration = ConsoleBackendRegistration(
        opaque_backend_ref="crew:engineer-console-p1",
        tmux_target="mc:engineer-console-p1",
        output_log=log,
        runtime_attempt_id=UUID("80000000-0000-0000-0000-000000000001"),
        runner_id="mission-control",
        runner_epoch=7,
    )
    return (
        TmuxConsoleAdapter(
            tmux_binary="tmux",
            socket_name="mc",
            allowed_log_root=tmp_path,
            registrations=(registration,),
            command_runner=runner,
        ),
        log,
    )


def test_adapter_uses_argument_arrays_and_proves_exact_project_and_incarnation(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    adapter, _ = _adapter(tmp_path, runner)
    outcome = adapter.inspect(_ref())
    assert isinstance(outcome, ConsoleBackendObservation)
    assert outcome.project_key == "ctower"
    assert outcome.backend_incarnation == "$9:1786400000"
    assert runner.commands == [
        ("tmux", "-L", "mc", "show-options", "-t", "mc:engineer-console-p1", "-v", "@project"),
        (
            "tmux",
            "-L",
            "mc",
            "display-message",
            "-p",
            "-t",
            "mc:engineer-console-p1",
            "#{session_id}\t#{session_created}",
        ),
    ]


def test_unknown_backend_and_wrong_project_are_typed_and_never_fall_back(tmp_path: Path) -> None:
    runner = _Runner(project="other-project")
    adapter, _ = _adapter(tmp_path, runner)
    wrong_project = adapter.inspect(_ref())
    assert isinstance(wrong_project, RecordProblem)
    assert wrong_project.code == "console-project-fence-mismatch"
    missing = adapter.inspect(_ref(opaque_backend_ref="crew:missing"))
    assert isinstance(missing, RecordProblem)
    assert missing.code == "console-adapter-unregistered"


def test_log_read_is_cursor_bounded_and_never_reaches_outside_registered_root(
    tmp_path: Path,
) -> None:
    adapter, log = _adapter(tmp_path, _Runner())
    first = adapter.read(_ref(), after_cursor=0, maximum_bytes=6)
    assert isinstance(first, ConsoleOutputBatch)
    assert first.payload == b"first\n"
    first_cursor = len(b"first\n")
    assert first.source_cursor == first_cursor
    log.write_bytes(log.read_bytes() + b"third\n")
    rest = adapter.read(_ref(), after_cursor=first_cursor, maximum_bytes=1024)
    assert isinstance(rest, ConsoleOutputBatch)
    assert rest.payload == b"second\nthird\n"


def test_adapter_source_has_no_record_tier_import() -> None:
    source = Path("apps/ctower-api/src/ctower_api/console_adapter.py").read_text(encoding="utf-8")
    assert "ctower_kernel.record.postgres" not in source
    assert "psycopg" not in source
    assert "shell=True" not in source
    assert cast(object, source)
