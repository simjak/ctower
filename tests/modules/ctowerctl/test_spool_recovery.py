"""Incremental recovery and automatic retention at the public ctowerctl boundary."""

from __future__ import annotations

import io
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

import pytest

from ctowerctl import interface
from ctowerctl._output import ExitCode
from ctowerctl.spool import ReplayResponse, Spool, SpoolCommand, _keyring
from ctowerctl.spool import _replay as replay
from ctowerctl.spool import interface as spool_interface
from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._models import QuarantineReceipt
from ctowerctl.spool._recovery import utc_text

__all__: tuple[str, ...] = ()

_TEN_THOUSAND_RECORD_COMMANDS = 5_000
_TEN_THOUSAND_RECORD_LIMIT_SECONDS = 2.0
_ELEVEN_MIB_COMMANDS = 1_111
_ELEVEN_MIB_TEXT_BYTES = 8_000
_ELEVEN_MIB = 11 * 1024 * 1024
_ELEVEN_MIB_LIMIT_SECONDS = 1.0
_ACCEPTED_RECORDS = 2
_CREDENTIAL = "synthetic-recovery-identity"
_ORIGIN = "https://recovery.example/api"


class _Backend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


class _ClientContext:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback


class _BarrierExecutor:
    def __init__(self, _client: object) -> None:
        self.observations: dict[UUID, object] = {}

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        del command
        return ReplayResponse(status_code=403, problem_code="synthetic_barrier")


class _Accepting:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
            response={"accepted": True},
        )


class _PastDateTime(datetime):
    @classmethod
    def now(cls, tz: object | None = None) -> _PastDateTime:
        del tz
        value = datetime.now(UTC) - timedelta(days=31)
        return cls.fromtimestamp(value.timestamp(), UTC)


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    backend = _Backend()
    monkeypatch.setattr(_keyring, "_secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return state


def test_inbox_notify_ten_thousand_record_recovery_is_under_two_seconds(
    protected_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spool = Spool.for_origin(_ORIGIN).bind_credential(_CREDENTIAL)
    with monkeypatch.context() as seed:
        seed.setattr(os, "fsync", lambda _descriptor: None)
        _seed_quarantined(spool, _TEN_THOUSAND_RECORD_COMMANDS)
    records = tuple(_origin_root(protected_state).rglob("*.rec"))
    assert len(records) == _TEN_THOUSAND_RECORD_COMMANDS * 2
    monkeypatch.setattr(interface, "CtowerClient", _ClientContext)
    monkeypatch.setattr(interface, "GeneratedReplayExecutor", _BarrierExecutor)

    first_code, _first_elapsed = _notify()
    second_code, second_elapsed = _notify()

    assert first_code is ExitCode.PERMANENT
    assert second_code is ExitCode.PERMANENT
    print(
        "T033_PERF "
        f"records={len(records)} second_seconds={second_elapsed:.6f} "
        f"limit={_TEN_THOUSAND_RECORD_LIMIT_SECONDS:.1f}"
    )
    assert second_elapsed < _TEN_THOUSAND_RECORD_LIMIT_SECONDS


def test_inbox_notify_eleven_mib_warm_recovery_is_under_one_second(
    protected_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spool = Spool.for_origin(_ORIGIN).bind_credential(_CREDENTIAL)
    with monkeypatch.context() as seed:
        seed.setattr(os, "fsync", lambda _descriptor: None)
        _seed_quarantined(
            spool,
            _ELEVEN_MIB_COMMANDS,
            text_bytes=_ELEVEN_MIB_TEXT_BYTES,
        )
    records = tuple(_origin_root(protected_state).rglob("*.rec"))
    assert sum(record.stat().st_size for record in records) >= _ELEVEN_MIB
    monkeypatch.setattr(interface, "CtowerClient", _ClientContext)
    monkeypatch.setattr(interface, "GeneratedReplayExecutor", _BarrierExecutor)

    first_code, _first_elapsed = _notify()
    second_code, second_elapsed = _notify()

    assert first_code is ExitCode.PERMANENT
    assert second_code is ExitCode.PERMANENT
    print(
        "T033_PERF "
        f"bytes={sum(record.stat().st_size for record in records)} "
        f"second_seconds={second_elapsed:.6f} limit={_ELEVEN_MIB_LIMIT_SECONDS:.1f}"
    )
    assert second_elapsed < _ELEVEN_MIB_LIMIT_SECONDS


def test_recovery_cursor_tamper_fails_closed(
    protected_state: Path,
) -> None:
    spool = Spool.for_origin(_ORIGIN)
    assert spool.status().health == "healthy"
    cursor = _origin_root(protected_state) / "recovery"
    data = bytearray(cursor.read_bytes())
    data[len(data) // 2] ^= 1
    cursor.write_bytes(data)

    status = spool.status()

    assert status.health == "state_unknown"
    assert status.reason_codes == ("chain_integrity",)


def test_old_accepted_history_compacts_on_an_ordinary_session(
    protected_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spool = Spool.for_origin(_ORIGIN).bind_credential(_CREDENTIAL)
    spool.enqueue(_command("old accepted"))
    with monkeypatch.context() as clock:
        clock.setattr(replay, "datetime", _PastDateTime)
        assert spool.drain(_Accepting()).accepted == 1
    root = _origin_root(protected_state)
    assert len(tuple(root.joinpath("accepted").glob("*.rec"))) == _ACCEPTED_RECORDS

    status = spool.status()

    assert status.accepted_count == 0
    assert len(tuple(root.joinpath("anchors").glob("*.anchor.rec"))) == 1


def _seed_quarantined(spool: Spool, count: int, *, text_bytes: int = 0) -> None:
    binding = spool._identity_binding
    assert binding is not None
    with spool._session() as session:
        for index in range(count):
            command = _command(f"seed-{index}" + "x" * text_bytes)
            envelope = spool_interface._new_envelope(
                command,
                spool._origin_digest,
                30,
                spool_interface._semantic_digest(command),
                binding,
            )
            record = session.append(RecordType.COMMAND, "pending", envelope)
            receipt = QuarantineReceipt(
                schema_version=2,
                command_sequence=record.stored.sequence,
                command_hash=record.opened.record_hash,
                reason_code="temporary_server_response",
                response_digest=None,
                quarantined_at=utc_text(),
                refusal=None,
            )
            session.append(RecordType.QUARANTINE_RECEIPT, "quarantine", receipt)
            session.move(record, "quarantine")


def _notify() -> tuple[ExitCode, float]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    started = time.perf_counter()
    code = interface.main(
        [
            "--base-url",
            _ORIGIN,
            "inbox",
            "notify",
            "--command-id",
            str(uuid4()),
            "--to",
            "qa-agent",
            "--severity",
            "info",
            "--project-key",
            "ctower",
            "Warm recovery benchmark.",
        ],
        stdin=io.StringIO(f"{_CREDENTIAL}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    elapsed = time.perf_counter() - started
    assert stderr.getvalue() == ""
    return ExitCode(code), elapsed


def _command(text: str) -> SpoolCommand:
    return SpoolCommand(
        operation_id="ingestInboxNotification",
        command_id=uuid4(),
        request_body={
            "project_key": "ctower",
            "severity": "info",
            "to": "qa-agent",
            "text": text,
        },
    )


def _origin_root(state: Path) -> Path:
    origins = tuple((state / "ctower" / "spool" / "v1").iterdir())
    assert len(origins) == 1
    return origins[0]
