import io
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ctowerctl import interface
from ctowerctl._output import ExitCode
from ctowerctl.spool import ReplayResponse, Spool, SpoolCommand, SpoolConfig, _keyring
from ctowerctl.spool import _replay as replay
from ctowerctl.spool import interface as spool_interface
from ctowerctl.spool._crypto import RecordType
from ctowerctl.spool._models import QuarantineReceipt
from ctowerctl.spool._recovery import RecoveredRecord, Session, utc_text

__all__: tuple[str, ...] = ()

_CREDENTIAL, _ORIGIN = "synthetic-recovery-identity", "https://recovery.example/api"


class _Accepting:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
        )


class _PastDateTime(datetime):
    @classmethod
    def now(cls, tz: object | None = None) -> "_PastDateTime":  # noqa: ARG003
        return cls.fromtimestamp((datetime.now(UTC) - timedelta(days=31)).timestamp(), UTC)


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(_keyring, "create_master_key", lambda _spool_uuid: b"x" * 32)
    monkeypatch.setattr(_keyring, "load_master_key", lambda _spool_uuid: b"x" * 32)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path / "state"


@pytest.mark.parametrize("case", [(5_000, 0, 2.0), (1_111, 8_000, 1.0)])
def test_inbox_notify_warm_recovery_meets_fleet_bounds(
    protected_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[int, int, float],
) -> None:
    count, text_bytes, limit = case
    spool = Spool.for_origin(_ORIGIN).bind_credential(_CREDENTIAL)
    with monkeypatch.context() as seed:
        seed.setattr(os, "fsync", lambda _descriptor: None)
        _seed_quarantined(spool, count, text_bytes=text_bytes)
    records = tuple(protected_state.rglob("*.rec"))
    total_bytes = sum(record.stat().st_size for record in records)
    minimum_bytes = 11 * 1024 * 1024 if text_bytes else 0
    assert len(records) == count * 2 and total_bytes >= minimum_bytes
    spool._path.joinpath("recovery").unlink()
    executor = MagicMock(observations={})
    executor.execute.return_value = ReplayResponse(status_code=403, problem_code="x")
    monkeypatch.setattr(interface, "CtowerClient", MagicMock())
    monkeypatch.setattr(interface, "GeneratedReplayExecutor", lambda _client: executor)
    with monkeypatch.context() as repair:
        repair.setattr(os, "fsync", lambda _descriptor: None)
        repair.setattr(Session, "move", MagicMock(side_effect=AssertionError))
        assert spool.status().quarantine_count == count
    _notify()
    code, elapsed = _notify()
    assert code is ExitCode.PERMANENT and elapsed < limit


def test_recovery_cursor_tamper_fails_closed(protected_state: Path) -> None:
    spool = Spool.for_origin(_ORIGIN)
    assert protected_state in spool._path.parents and spool.status().health == "healthy"
    cursor = spool._path / "recovery"
    data = bytearray(cursor.read_bytes())
    data[len(data) // 2] ^= 1
    cursor.write_bytes(data)
    status = spool.status()
    assert status.health == "state_unknown" and status.reason_codes == ("chain_integrity",)


def test_compaction_survives_corruption_and_scan_bound_crash(
    protected_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spool = Spool.for_origin(_ORIGIN).bind_credential(_CREDENTIAL)
    spool.enqueue(_command("old accepted"))
    with monkeypatch.context() as clock:
        clock.setattr(replay, "datetime", _PastDateTime)
        assert spool.drain(_Accepting()).accepted == 1
    with spool._session(automatic_compaction=False) as session:
        corrupt = _append_pending(spool, session, "corrupt")
    path = next(spool._path.joinpath("pending").glob("*.command.rec"))
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(data)
    artifact = spool.list_entries()[-1]
    spool.discard(corrupt.stored.sequence, "reviewed", artifact_digest=artifact.artifact_digest)
    config = SpoolConfig(
        state_path=protected_state / "bounded", max_live_commands=50, max_scan_entries=100
    )
    spool = Spool.for_origin(_ORIGIN, config).bind_credential(_CREDENTIAL)
    monkeypatch.setattr(os, "fsync", lambda _descriptor: None)
    for index in range(config.max_live_commands):
        spool.enqueue(_command(f"accepted-{index}"))
    with monkeypatch.context() as clock:
        clock.setattr(replay, "datetime", _PastDateTime)
        assert spool.drain(_Accepting()).accepted == config.max_live_commands
    rename = os.rename

    def fail_head(source: str, destination: str, **kwargs: int) -> None:
        if destination == "head":
            raise OSError("stop")
        rename(source, destination, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(os, "rename", fail_head)
        assert spool.status().health == "state_unknown"
    assert (status := spool.status()).chain_status == "healthy" and status.accepted_count == 0
    assert status.health == "degraded" and status.reason_codes == ("torn_write",)


def _append_pending(spool: Spool, session: Session, text: str) -> RecoveredRecord:
    command = _command(text)
    binding = spool._identity_binding
    assert binding is not None
    return session.append(
        RecordType.COMMAND,
        "pending",
        spool_interface._new_envelope(
            command, spool._origin_digest, 30, spool_interface._semantic_digest(command), binding
        ),
    )


def _seed_quarantined(spool: Spool, count: int, *, text_bytes: int) -> None:
    with spool._session() as session:
        for index in range(count):
            record = _append_pending(spool, session, f"seed-{index}" + "x" * text_bytes)
            session.append(
                RecordType.QUARANTINE_RECEIPT,
                "quarantine",
                QuarantineReceipt(
                    schema_version=2,
                    command_sequence=record.stored.sequence,
                    command_hash=record.opened.record_hash,
                    reason_code="temporary_server_response",
                    response_digest=None,
                    quarantined_at=utc_text(),
                ),
            )


def _notify() -> tuple[ExitCode, float]:
    started = time.perf_counter()
    code = interface.main(
        f"--base-url {_ORIGIN} inbox notify --command-id {uuid4()} --to qa-agent "
        "--severity info --project-key ctower benchmark".split(),
        stdin=io.StringIO(f"{_CREDENTIAL}\n"),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    return ExitCode(code), time.perf_counter() - started


def _command(text: str) -> SpoolCommand:
    return SpoolCommand(
        operation_id="ingestInboxNotification",
        command_id=uuid4(),
        request_body={"project_key": "ctower", "severity": "info", "to": "qa-agent", "text": text},
    )
