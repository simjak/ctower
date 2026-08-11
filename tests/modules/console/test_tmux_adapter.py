"""RED-first tests for the registered, read-only tmux/log Adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess
from typing import cast
from uuid import UUID

import pytest

from ctower_api.console_adapter import ConsoleBackendRegistration, TmuxConsoleAdapter
from ctower_kernel.console import ConsoleBackendObservation, ConsoleOutputBatch, ConsoleSessionRef
from ctower_kernel.record import RecordProblem

_IDENTITY_INVOCATIONS = 2
_REPLACEMENT_EPOCH = 8
_READ_INCARNATION_INVOCATION = 2


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


def _adapter(
    tmp_path: Path, runner: _Runner
) -> tuple[TmuxConsoleAdapter, Path, dict[str, ConsoleBackendRegistration]]:
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
    registrations = {registration.opaque_backend_ref: registration}
    return (
        TmuxConsoleAdapter(
            tmux_binary="tmux",
            socket_name="mc",
            allowed_log_root=tmp_path,
            registration_reader=registrations.get,
            command_runner=runner,
        ),
        log,
        registrations,
    )


def test_adapter_uses_argument_arrays_and_proves_exact_project_and_incarnation(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    adapter, _, _ = _adapter(tmp_path, runner)
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
    adapter, _, _ = _adapter(tmp_path, runner)
    wrong_project = adapter.inspect(_ref())
    assert isinstance(wrong_project, RecordProblem)
    assert wrong_project.code == "console-project-fence-mismatch"
    missing = adapter.inspect(_ref(opaque_backend_ref="crew:missing"))
    assert isinstance(missing, RecordProblem)
    assert missing.code == "console-adapter-unregistered"


def test_each_observation_reads_current_runtime_runner_epoch_registration(tmp_path: Path) -> None:
    adapter, _, registrations = _adapter(tmp_path, _Runner())
    initial = adapter.inspect(_ref())
    assert isinstance(initial, ConsoleBackendObservation)
    current = registrations["crew:engineer-console-p1"]
    registrations[current.opaque_backend_ref] = replace(
        current,
        runtime_attempt_id=UUID("80000000-0000-0000-0000-000000000002"),
        runner_id="replacement-runner",
        runner_epoch=_REPLACEMENT_EPOCH,
    )

    replacement = adapter.inspect(_ref())

    assert isinstance(replacement, ConsoleBackendObservation)
    assert replacement.runtime_attempt_id != initial.runtime_attempt_id
    assert replacement.runner_id == "replacement-runner"
    assert replacement.runner_epoch == _REPLACEMENT_EPOCH


def test_log_read_is_cursor_bounded_and_never_reaches_outside_registered_root(
    tmp_path: Path,
) -> None:
    adapter, log, _ = _adapter(tmp_path, _Runner())
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
    assert "capture-pane" not in source
    assert "send-keys" not in source
    assert "terminal-read" not in source
    assert "terminal_read" not in source
    assert source.count("self._invoke(") == _IDENTITY_INVOCATIONS
    assert 'self._invoke("show-options"' in source
    assert 'self._invoke(\n            "display-message"' in source
    assert cast(object, source)


def test_registration_and_adapter_configuration_fail_closed(tmp_path: Path) -> None:
    log = tmp_path / "console.log"
    log.write_bytes(b"output")
    with pytest.raises(ValueError, match="identity"):
        ConsoleBackendRegistration(
            "", "target", log, _ref().runtime_attempt_id, "mission-control", 1
        )
    with pytest.raises(ValueError, match="epoch"):
        ConsoleBackendRegistration(
            "backend", "target", log, _ref().runtime_attempt_id, "mission-control", 0
        )
    with pytest.raises(ValueError, match="explicit"):
        TmuxConsoleAdapter(
            tmux_binary="",
            socket_name="mc",
            allowed_log_root=tmp_path,
            registration_reader=lambda _opaque: None,
        )

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    registration = ConsoleBackendRegistration(
        "backend", "target", log, _ref().runtime_attempt_id, "mission-control", 1
    )
    outside = TmuxConsoleAdapter(
        tmux_binary="tmux",
        socket_name="mc",
        allowed_log_root=allowed,
        registration_reader={registration.opaque_backend_ref: registration}.get,
    )
    refused = outside.inspect(_ref(opaque_backend_ref="backend"))
    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-adapter-unregistered"


def test_tmux_process_and_incarnation_failures_are_typed(tmp_path: Path) -> None:
    def absent(command: tuple[str, ...]) -> CompletedProcess[str]:
        return CompletedProcess(command, 1, stdout="", stderr="absent")

    unavailable, _, _ = _adapter(tmp_path, cast(_Runner, absent))
    project_problem = unavailable.inspect(_ref())
    assert isinstance(project_problem, RecordProblem)
    assert project_problem.code == "console-backend-unavailable"

    def incarnation(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command[-2:] == ("-v", "@project"):
            return CompletedProcess(command, 0, stdout="ctower\n", stderr="")
        return CompletedProcess(command, 1, stdout="", stderr="absent")

    unavailable, _, _ = _adapter(tmp_path, cast(_Runner, incarnation))
    incarnation_problem = unavailable.inspect(_ref())
    assert isinstance(incarnation_problem, RecordProblem)
    assert incarnation_problem.code == "console-backend-unavailable"

    def malformed(command: tuple[str, ...]) -> CompletedProcess[str]:
        if command[-2:] == ("-v", "@project"):
            return CompletedProcess(command, 0, stdout="ctower\n", stderr="")
        return CompletedProcess(command, 0, stdout="missing-delimiter\n", stderr="")

    malformed_adapter, _, _ = _adapter(tmp_path, cast(_Runner, malformed))
    malformed_problem = malformed_adapter.inspect(_ref())
    assert isinstance(malformed_problem, RecordProblem)
    assert malformed_problem.code == "console-adapter-malformed"


def test_log_read_refuses_invalid_ranges_and_reports_truncation(tmp_path: Path) -> None:
    adapter, log, _ = _adapter(tmp_path, _Runner())
    for ref, cursor, maximum, code in (
        (_ref(adapter_key="other-v1"), 0, 1, "console-adapter-unregistered"),
        (_ref(), -1, 1, "console-cursor-invalid"),
        (_ref(), 0, 0, "console-cursor-invalid"),
    ):
        outcome = adapter.read(ref, after_cursor=cursor, maximum_bytes=maximum)
        assert isinstance(outcome, RecordProblem)
        assert outcome.code == code

    truncated = adapter.read(_ref(), after_cursor=log.stat().st_size + 1, maximum_bytes=1)
    assert isinstance(truncated, ConsoleOutputBatch)
    assert truncated.gap
    assert truncated.gap_reason == "source-truncated"
    log.unlink()
    absent = adapter.read(_ref(), after_cursor=0, maximum_bytes=1)
    assert isinstance(absent, RecordProblem)
    assert absent.code == "console-output-unavailable"


def test_log_read_refuses_a_symlink_even_when_it_resolves_beneath_the_root(
    tmp_path: Path,
) -> None:
    adapter, log, registrations = _adapter(tmp_path, _Runner())
    link = tmp_path / "linked.log"
    link.symlink_to(log)
    current = registrations["crew:engineer-console-p1"]
    registrations[current.opaque_backend_ref] = replace(current, output_log=link)

    refused = adapter.read(_ref(), after_cursor=0, maximum_bytes=1)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-output-unavailable"


def test_registry_replacement_during_read_returns_no_output_batch(tmp_path: Path) -> None:
    runner = _Runner()
    _adapter_instance, _log, registrations = _adapter(tmp_path, runner)
    original = registrations["crew:engineer-console-p1"]
    calls = 0

    def replace_during_read(command: tuple[str, ...]) -> CompletedProcess[str]:
        nonlocal calls
        calls += 1
        outcome = runner(command)
        if calls == _READ_INCARNATION_INVOCATION:
            registrations[original.opaque_backend_ref] = replace(
                original,
                runtime_attempt_id=UUID("80000000-0000-0000-0000-000000000002"),
            )
        return outcome

    racing = TmuxConsoleAdapter(
        tmux_binary="tmux",
        socket_name="mc",
        allowed_log_root=tmp_path,
        registration_reader=registrations.get,
        command_runner=replace_during_read,
    )

    refused = racing.read(_ref(), after_cursor=0, maximum_bytes=6)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-runtime-attempt-fenced"
