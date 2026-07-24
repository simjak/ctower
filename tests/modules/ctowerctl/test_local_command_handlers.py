"""Branch coverage for local spool, operations, and CLI composition boundaries."""

from __future__ import annotations

import argparse
import io
from datetime import UTC, datetime, timedelta
from typing import NoReturn, cast
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from ctower_client import CtowerClient, CtowerProblemError
from ctower_client.models import PoisonDispositionRequest, Problem
from ctower_client.operations import operation_for_cli
from ctowerctl import _ops_commands, _spool_commands, interface
from ctowerctl._generated_replay import ReplayObservation
from ctowerctl._output import ExitCode
from ctowerctl.spool import (
    DrainReport,
    ReplayResponse,
    Spool,
    SpoolDoctorReport,
    SpoolEntry,
    SpoolError,
    SpoolState,
    SpoolStatus,
)

__all__: tuple[str, ...] = ()

_SEQUENCE = 7


def test_operations_handlers_build_and_route_only_authored_commands() -> None:
    outbox_id = uuid4()
    payload = _ops_commands.build_mutation(
        argparse.Namespace(
            outbox_id=outbox_id,
            consumer_key="projection.ticket",
            topic="ticket.events",
            action="retry",
            reason="Operator inspected the poison event.",
        )
    )

    assert isinstance(payload.request, PoisonDispositionRequest)
    assert payload.request.action == "retry"
    assert payload.path_parameters == {"outbox_id": str(outbox_id)}

    client = _OperationsClient()
    health = _ops_commands.execute_query(
        argparse.Namespace(cli_name="control health"),
        cast(CtowerClient, client),
    )
    custodian_id = uuid4()
    assignee_id = uuid4()
    board = _ops_commands.execute_query(
        argparse.Namespace(
            cli_name="board query",
            lane="in_review",
            priority="P1",
            stage_key="verification",
            custodian_id=custodian_id,
            assignee_id=assignee_id,
        ),
        cast(CtowerClient, client),
    )

    assert cast(_Result, health).marker == "health"
    assert cast(_Result, board).marker == "board"
    assert client.calls == ["health", "board"]
    assert client.board_filters == (
        "in_review",
        "P1",
        "verification",
        custodian_id,
        assignee_id,
    )
    with pytest.raises(ValueError, match="unsupported operations query"):
        _ops_commands.execute_query(
            argparse.Namespace(cli_name="ops invent"),
            cast(CtowerClient, client),
        )


def test_local_spool_reports_health_and_inventory(spool_harness: _FakeSpool) -> None:
    spool = spool_harness
    result, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments("spool status"),
        io.StringIO(),
    )
    assert result == spool.status_result
    assert code is ExitCode.SUCCESS
    spool.status_result = _spool_status(healthy=False)
    _, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments("spool status"),
        io.StringIO(),
    )
    assert code is ExitCode.LOCAL_FAILURE

    for state, expected in (("pending", SpoolState.PENDING), (None, None)):
        result, code = _spool_commands.execute(
            "https://ctower.example",
            _local_arguments("spool list", state=state, limit=3),
            io.StringIO(),
        )
        assert result.model_dump()["entries"][0]["sequence"] == _SEQUENCE
        assert code is ExitCode.SUCCESS
        assert spool.list_calls[-1] == (expected, 3)
    _spool_commands.execute(
        "https://ctower.example",
        _local_arguments("spool quarantine list", state=None, limit=4),
        io.StringIO(),
    )
    assert spool.list_calls[-1] == (SpoolState.QUARANTINE, 4)

    _, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments("spool doctor"),
        io.StringIO(),
    )
    assert code is ExitCode.SUCCESS
    spool.doctor_result = _doctor(healthy=False)
    _, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments("spool doctor"),
        io.StringIO(),
    )
    assert code is ExitCode.LOCAL_FAILURE


def test_local_spool_applies_explicit_dispositions(spool_harness: _FakeSpool) -> None:
    spool = spool_harness
    retry, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments(
            "spool retry",
            sequence=_SEQUENCE,
            reason="Retry after inspection.",
        ),
        io.StringIO(),
    )
    assert retry == spool.entries[0]
    assert code is ExitCode.SUCCESS
    disposition, code = _spool_commands.execute(
        "https://ctower.example",
        _local_arguments(
            "spool discard",
            sequence=_SEQUENCE,
            reason="Discard after inspection.",
        ),
        io.StringIO(),
    )
    assert disposition.model_dump() == {"action": "discard", "sequence": _SEQUENCE}
    assert code is ExitCode.SUCCESS
    assert spool.retry_calls == [(_SEQUENCE, "Retry after inspection.")]
    assert spool.discard_calls == [(_SEQUENCE, "Discard after inspection.")]


def test_local_spool_maps_drain_outcomes_and_refuses_unknown(
    spool_harness: _FakeSpool,
) -> None:
    spool = spool_harness
    reports = (
        (_drain_report(remaining=0, barrier=_SEQUENCE), ExitCode.PERMANENT),
        (_drain_report(remaining=2, barrier=None), ExitCode.TEMPORARY),
        (_drain_report(remaining=0, barrier=None), ExitCode.SUCCESS),
    )
    for report, expected_code in reports:
        spool.drain_result = report
        result, code = _spool_commands.execute(
            "https://ctower.example",
            _local_arguments("spool drain"),
            io.StringIO("ephemeral-authority\n"),
        )
        assert result == report
        assert code is expected_code
    assert spool.drain_calls == len(reports)

    with pytest.raises(ValueError, match="unsupported local spool command"):
        _spool_commands.execute(
            "https://ctower.example",
            _local_arguments("spool invent"),
            io.StringIO(),
        )


def test_interface_dispatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outbox_id = uuid4()
    ops_arguments = argparse.Namespace(
        area="ops",
        outbox_id=outbox_id,
        consumer_key="projection.ticket",
        topic="ticket.events",
        action="tombstone",
        reason="Poison event is permanently invalid.",
    )
    payload = interface._build_mutation(ops_arguments)
    assert isinstance(payload.request, PoisonDispositionRequest)
    with pytest.raises(ValueError, match="unsupported mutation family"):
        interface._build_mutation(argparse.Namespace(area="invented"))

    client = _OperationsClient()
    query = interface._execute_query(
        argparse.Namespace(
            area="board",
            cli_name="board query",
            lane=None,
            priority=None,
            stage_key=None,
            custodian_id=None,
            assignee_id=None,
        ),
        cast(CtowerClient, client),
    )
    assert cast(_Result, query).marker == "board"
    with pytest.raises(ValueError, match="unsupported query family"):
        interface._execute_query(
            argparse.Namespace(area="invented"),
            cast(CtowerClient, client),
        )

    local_result = _Result(marker="local")
    monkeypatch.setattr(
        _spool_commands,
        "execute",
        lambda _base_url, _arguments, _stream: (local_result, ExitCode.SUCCESS),
    )
    assert interface._execute(
        argparse.Namespace(
            base_url="https://ctower.example",
            local_command="spool status",
        ),
        io.StringIO(),
    ) == (local_result, ExitCode.SUCCESS)
    with pytest.raises(ValueError, match="absent from generated registry"):
        interface._execute(
            argparse.Namespace(
                base_url="https://ctower.example",
                cli_name="ticket invent",
            ),
            io.StringIO(),
        )

    forbidden = operation_for_cli("bootstrap first-tenant")
    assert forbidden is not None
    with pytest.raises(ValueError, match="not allowlisted"):
        interface._execute_mutation(
            "https://ctower.example",
            "ephemeral-authority",
            argparse.Namespace(command_id=uuid4()),
            forbidden,
        )


def test_interface_outcome_helpers_fail_closed() -> None:
    spool = _FakeSpool()
    outbox_id = uuid4()
    accepted = _entry(SpoolState.ACCEPTED_ARCHIVE)
    pending = _entry(SpoolState.PENDING)
    quarantined = _entry(SpoolState.QUARANTINE, reason_code="schema-invalid")
    states = [interface._outcome_state(entry.state) for entry in (accepted, pending, quarantined)]
    assert states == [
        "accepted",
        "queued",
        "quarantined",
    ]
    assert interface._outcome_reason(accepted, "unused") == "accepted"
    assert interface._outcome_reason(pending, "network-offline") == "network_offline"
    assert interface._outcome_reason(quarantined, "unused") == "schema_invalid"
    assert interface._outcome_code(accepted.state, None) is ExitCode.SUCCESS
    assert interface._outcome_code(quarantined.state, None) is ExitCode.PERMANENT
    assert interface._outcome_code(pending.state, 7) is ExitCode.PERMANENT
    assert interface._outcome_code(pending.state, None) is ExitCode.TEMPORARY

    response = ReplayResponse(status_code=202, response={"accepted": True})
    assert interface._observation_result(None) is None
    assert interface._observation_result(ReplayObservation(response)) == {"accepted": True}
    problem = _problem()
    observed_problem = interface._observation_result(ReplayObservation(response, problem))
    assert observed_problem is not None
    assert observed_problem["code"] == "validation-error"

    spool.entries = (_entry(SpoolState.PENDING), accepted)
    assert accepted.command_id is not None
    assert interface._current_entry(cast(Spool, spool), accepted.command_id) == accepted
    with pytest.raises(
        SpoolError,
        match="spooled command disappeared",
    ):
        interface._current_entry(cast(Spool, spool), uuid4())
    assert interface._command_id(argparse.Namespace(command_id=outbox_id)) == outbox_id
    assert interface._command_id(argparse.Namespace(command_id=str(outbox_id))) is None


def test_interface_maps_usage_problem_and_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = io.StringIO()
    assert interface.main(["invented"], stderr=stderr) == int(ExitCode.USAGE)
    assert stderr.getvalue().startswith("usage:")

    arguments = argparse.Namespace(command_id=uuid4())
    monkeypatch.setattr(interface, "_execute", lambda *_args: _raise(ValueError("invalid")))
    assert _run(arguments)[0] == int(ExitCode.USAGE)

    problem = _problem()
    monkeypatch.setattr(
        interface,
        "_execute",
        lambda *_args: _raise(CtowerProblemError(_ProblemForError(problem))),
    )
    code, output, error = _run(arguments)
    assert code == int(ExitCode.PERMANENT)
    assert output == ""
    assert '"code":"validation-error"' in error

    request = httpx.Request("GET", "https://ctower.example")
    monkeypatch.setattr(
        interface,
        "_execute",
        lambda *_args: _raise(httpx.ConnectError("offline", request=request)),
    )
    code, _, error = _run(arguments)
    assert code == int(ExitCode.TEMPORARY)
    assert f"command_id={arguments.command_id}" in error
    code, _, error = _run(argparse.Namespace())
    assert code == int(ExitCode.TEMPORARY)
    assert "temporary query" in error


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    marker: str


class _OperationsClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.board_filters: tuple[
            str | None,
            str | None,
            str | None,
            UUID | None,
            UUID | None,
        ] = (None, None, None, None, None)

    def get_control_health(self) -> _Result:
        self.calls.append("health")
        return _Result(marker="health")

    def get_board(
        self,
        *,
        lane: str | None,
        priority: str | None,
        stage_key: str | None,
        custodian_id: UUID | None,
        assignee_id: UUID | None,
    ) -> _Result:
        self.calls.append("board")
        self.board_filters = (lane, priority, stage_key, custodian_id, assignee_id)
        return _Result(marker="board")


class _ClientContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(
        self,
        _exception_type: object,
        _exception: object,
        _traceback: object,
    ) -> None:
        return None


class _FakeSpool:
    def __init__(self) -> None:
        self.entries: tuple[SpoolEntry, ...] = (_entry(SpoolState.PENDING),)
        self.status_result = _spool_status(healthy=True)
        self.doctor_result = _doctor(healthy=True)
        self.drain_result = _drain_report(remaining=0, barrier=None)
        self.list_calls: list[tuple[SpoolState | None, int]] = []
        self.retry_calls: list[tuple[int, str]] = []
        self.discard_calls: list[tuple[int, str]] = []
        self.drain_calls = 0

    def status(self) -> SpoolStatus:
        return self.status_result

    def list_entries(
        self,
        state: SpoolState | None = None,
        *,
        limit: int,
    ) -> tuple[SpoolEntry, ...]:
        self.list_calls.append((state, limit))
        return self.entries

    def doctor(self) -> SpoolDoctorReport:
        return self.doctor_result

    def retry(self, sequence: int, reason: str) -> SpoolEntry:
        self.retry_calls.append((sequence, reason))
        return self.entries[0]

    def discard(self, sequence: int, reason: str) -> None:
        self.discard_calls.append((sequence, reason))

    def drain(self, _executor: object) -> DrainReport:
        self.drain_calls += 1
        return self.drain_result


@pytest.fixture
def spool_harness(monkeypatch: pytest.MonkeyPatch) -> _FakeSpool:
    spool = _FakeSpool()
    monkeypatch.setattr(
        Spool,
        "for_origin",
        staticmethod(lambda _base_url: cast(Spool, spool)),
    )
    monkeypatch.setattr(
        _spool_commands,
        "CtowerClient",
        lambda *_args, **_kwargs: _ClientContext(),
    )
    monkeypatch.setattr(
        _spool_commands,
        "GeneratedReplayExecutor",
        lambda _client: object(),
    )
    return spool


def _entry(state: SpoolState, *, reason_code: str | None = None) -> SpoolEntry:
    now = datetime(2026, 7, 24, tzinfo=UTC)
    return SpoolEntry(
        sequence=_SEQUENCE,
        command_id=uuid4(),
        operation_id="createTicket",
        state=state,
        enqueued_at=now,
        expires_at=now + timedelta(days=1),
        bytes=128,
        reason_code=reason_code,
    )


def _spool_status(*, healthy: bool) -> SpoolStatus:
    if healthy:
        return SpoolStatus(
            origin_digest="a" * 64,
            health="healthy",
            pending_count=1,
            accepted_count=0,
            quarantine_count=0,
            pending_bytes=128,
            quarantine_bytes=0,
            oldest_pending_seconds=2.0,
            last_accepted_sequence=None,
            keyring_available=True,
            chain_status="healthy",
            reason_codes=(),
        )
    return SpoolStatus(
        origin_digest="a" * 64,
        health="degraded",
        pending_count=1,
        accepted_count=0,
        quarantine_count=0,
        pending_bytes=128,
        quarantine_bytes=0,
        oldest_pending_seconds=2.0,
        last_accepted_sequence=None,
        keyring_available=True,
        chain_status="degraded",
        reason_codes=(),
    )


def _doctor(*, healthy: bool) -> SpoolDoctorReport:
    if healthy:
        return SpoolDoctorReport(
            healthy=True,
            state="healthy",
            checks=("chain",),
            findings=(),
        )
    return SpoolDoctorReport(
        healthy=False,
        state="degraded",
        checks=("chain",),
        findings=("chain_invalid",),
    )


def _drain_report(*, remaining: int, barrier: int | None) -> DrainReport:
    return DrainReport(
        attempted=1,
        accepted=0 if remaining or barrier is not None else 1,
        quarantined=1 if barrier is not None else 0,
        remaining_pending=remaining,
        barrier_sequence=barrier,
        reason_code="barrier" if barrier is not None else "complete",
    )


def _local_arguments(command: str, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "local_command": command,
        "state": None,
        "limit": 100,
        "sequence": _SEQUENCE,
        "reason": "Operator disposition.",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _problem() -> Problem:
    return Problem(
        code="validation-error",
        detail="Generated request was refused.",
        status=422,
        title="Validation error",
        type_uri="urn:ctower:problem:validation-error",
    )


class _ProblemForError:
    """Mutable protocol adapter retaining the redacted generated problem shape."""

    def __init__(self, problem: Problem) -> None:
        self.code: str = problem.code
        self.detail: str = problem.detail
        self._problem = problem

    def model_dump(self, **_kwargs: object) -> dict[str, object]:
        return {
            "code": self._problem.code,
            "detail": self._problem.detail,
            "status": self._problem.status,
            "title": self._problem.title,
            "type": self._problem.type_uri,
        }


def _run(arguments: argparse.Namespace) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = interface._run_command(
        arguments,
        io.StringIO("ephemeral-authority\n"),
        stdout,
        stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def _raise(error: Exception) -> NoReturn:
    raise error
