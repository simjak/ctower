"""Real-filesystem, fault, tamper, recovery, and retention spool evidence."""

from __future__ import annotations

import errno
import json
import os
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from ctowerctl.spool import ReplayResponse, Spool, SpoolCommand, SpoolConfig, SpoolError

__all__: tuple[str, ...] = ()

_THIRTY_ONE_DAYS = 31
_TWO_RECORDS = 2

type _JsonScalar = str | int | float | bool | None
type _JsonValue = _JsonScalar | list[_JsonValue] | dict[str, _JsonValue]
type _JsonObject = dict[str, _JsonValue]


class _Backend:
    priority = 1.0

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


_Backend.__module__ = "keyring.backends.SecretService"
_Backend.__name__ = "Keyring"


@pytest.fixture
def secure_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("keyring")
    backend = _Backend()
    module.__dict__["get_keyring"] = lambda: backend
    monkeypatch.setitem(sys.modules, "keyring", module)


class _Accepting:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        self.calls += 1
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
        value = datetime.now(UTC) - timedelta(days=_THIRTY_ONE_DAYS)
        return cls.fromtimestamp(value.timestamp(), UTC)


def test_symlink_hardlink_and_network_filesystem_are_refused(
    tmp_path: Path,
    secure_keyring: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(SpoolError) as symlink_error:
        _spool(alias).enqueue(_command())
    assert symlink_error.value.code == "storage_integrity"

    state = tmp_path / "hardlink"
    spool = _spool(state)
    spool.enqueue(_command())
    record = next(_root(state).joinpath("pending").glob("*.rec"))
    os.link(record, record.with_name("hardlink-copy"))
    assert spool.status().health == "state_unknown"
    assert not spool.doctor().healthy

    mountinfo = "1 0 0:1 / / rw - nfs synthetic rw\n"
    original_read_text = Path.read_text

    def mounted_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == Path("/proc/self/mountinfo"):
            return mountinfo
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", mounted_read)
    with pytest.raises(SpoolError, match="failed closed") as network_error:
        _spool(tmp_path / "network").enqueue(_command())
    assert network_error.value.code == "storage_integrity"

    def unreadable_mountinfo(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        del encoding, errors
        if path == Path("/proc/self/mountinfo"):
            raise OSError("synthetic unavailable mount table")
        return original_read_text(path)

    monkeypatch.setattr(Path, "read_text", unreadable_mountinfo)
    with pytest.raises(SpoolError) as unknown_filesystem:
        _spool(tmp_path / "unknown-filesystem").enqueue(_command())
    assert unknown_filesystem.value.code == "storage_integrity"


def test_owner_only_intermediate_state_directories_are_reverified(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command())
    (state / "spool").chmod(0o755)

    assert spool.status().health == "state_unknown"
    assert not spool.doctor().healthy


def test_ciphertext_tamper_moves_pending_to_quarantine_and_blocks_chain(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command())
    record = next(_root(state).joinpath("pending").glob("*.rec"))
    data = bytearray(record.read_bytes())
    data[len(data) // 2] ^= 1
    record.write_bytes(data)

    status = spool.status()

    assert status.health == "state_unknown"
    assert "chain_integrity" in status.reason_codes
    assert not tuple(_root(state).joinpath("pending").glob("*.rec"))
    assert tuple(_root(state).joinpath("quarantine").glob("*.command.rec"))
    assert not spool.doctor().healthy


def test_old_authenticated_head_incorporates_one_unique_next_record(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command())
    head = _root(state) / "head"
    old_head = head.read_bytes()
    second = spool.enqueue(_command())
    current_head = head.read_bytes()
    head.write_bytes(old_head)

    entries = spool.list_entries()

    assert len(entries) == _TWO_RECORDS
    assert entries[-1].sequence == second.sequence
    assert head.read_bytes() == current_head
    assert spool.doctor().healthy


def test_durable_receipt_repairs_command_move_interrupted_by_crash(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    command = spool.enqueue(_command())
    assert spool.drain(_Accepting()).accepted == 1
    root = _root(state)
    accepted_command = next(root.joinpath("accepted").glob("*.command.rec"))
    accepted_command.rename(root / "pending" / accepted_command.name)

    assert not spool.doctor().healthy
    status = spool.status()

    assert status.accepted_count == 1
    assert status.pending_count == 0
    assert spool.list_entries()[0].sequence == command.sequence
    assert next(root.joinpath("accepted").glob("*.command.rec"))
    assert not tuple(root.joinpath("pending").glob("*.command.rec"))
    assert spool.doctor().healthy


def test_doctor_does_not_mutate_torn_temp_then_recovery_preserves_evidence(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command())
    temporary = _root(state) / "tmp" / f".record-{uuid4()}.tmp"
    temporary.write_bytes(b"uncommitted encrypted bytes")
    temporary.chmod(0o600)

    report = spool.doctor()

    assert not report.healthy
    assert temporary.exists()
    status = spool.status()
    assert status.health == "degraded"
    assert status.quarantine_count == 1
    assert not temporary.exists()
    assert tuple(_root(state).joinpath("quarantine").glob("*.evidence"))


def test_short_write_is_completed_and_enospc_eio_leave_no_pending_record(
    tmp_path: Path,
    secure_keyring: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    original_write = os.write

    def short_write(file_descriptor: int, data: bytes) -> int:
        return original_write(file_descriptor, data[: max(1, len(data) // 2)])

    monkeypatch.setattr(os, "write", short_write)
    short_spool = _spool(tmp_path / "short")
    assert short_spool.enqueue(_command()).sequence == 1
    monkeypatch.setattr(os, "write", original_write)

    for label, error_number in (("full", errno.ENOSPC), ("io", errno.EIO)):
        state = tmp_path / label

        def failed_write(file_descriptor: int, data: bytes, *, code: int = error_number) -> int:
            del file_descriptor, data
            raise OSError(code, "injected")

        monkeypatch.setattr(os, "write", failed_write)
        with pytest.raises(SpoolError) as storage_error:
            _spool(state).enqueue(_command())
        assert storage_error.value.code == "storage_integrity"
        monkeypatch.setattr(os, "write", original_write)
        assert _spool(state).status().pending_count == 0


def test_nonce_is_unique_and_headers_never_carry_request_content(
    tmp_path: Path,
    secure_keyring: None,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    corpus = "nonce-private-content-42ea"
    spool = _spool(state)
    spool.enqueue(_command({"body": corpus}))
    spool.enqueue(_command({"body": corpus + "-2"}))
    spool.drain(_Accepting())
    documents = [
        json.loads(path.read_text(encoding="utf-8")) for path in _root(state).rglob("*.rec")
    ]
    nonces = [item["header"]["nonce"] for item in documents]
    assert len(nonces) == len(set(nonces))
    assert corpus not in json.dumps(documents, sort_keys=True)


def test_old_accepted_history_compacts_to_one_anchor_but_quarantine_never_does(
    tmp_path: Path,
    secure_keyring: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    accepted_state = tmp_path / "accepted"
    accepted = _spool(accepted_state)
    accepted.enqueue(_command())
    with monkeypatch.context() as clock:
        clock.setattr("ctowerctl.spool._replay.datetime", _PastDateTime)
        accepted.drain(_Accepting())

    assert accepted.compact() == _TWO_RECORDS
    assert accepted.list_entries() == ()
    anchors = tuple(_root(accepted_state).joinpath("anchors").glob("*.anchor.rec"))
    assert len(anchors) == 1
    assert accepted.doctor().healthy

    quarantine = _spool(tmp_path / "quarantine")
    quarantine.enqueue(_command())
    quarantine.drain(_Rejecting())
    assert quarantine.compact() == 0
    assert quarantine.status().quarantine_count == 1


def test_interrupted_compaction_deletion_recovers_from_authenticated_anchor(
    tmp_path: Path,
    secure_keyring: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    state = tmp_path / "compaction-crash"
    spool = _spool(state)
    spool.enqueue(_command())
    with monkeypatch.context() as clock:
        clock.setattr("ctowerctl.spool._replay.datetime", _PastDateTime)
        spool.drain(_Accepting())
    original_unlink = os.unlink
    unlink_calls = 0

    def interrupted_unlink(path: str, *, dir_fd: int | None = None) -> None:
        nonlocal unlink_calls
        unlink_calls += 1
        if unlink_calls == _TWO_RECORDS:
            raise OSError(errno.EIO, "injected compaction interruption")
        original_unlink(path, dir_fd=dir_fd)

    with monkeypatch.context() as fault:
        fault.setattr(os, "unlink", interrupted_unlink)
        with pytest.raises(SpoolError) as interrupted:
            spool.compact()
    assert interrupted.value.code == "storage_integrity"
    assert not spool.doctor().healthy

    assert spool.status().accepted_count == 0
    assert spool.list_entries() == ()
    assert spool.doctor().healthy
    assert len(tuple(_root(state).joinpath("anchors").glob("*.anchor.rec"))) == 1


def test_expired_pending_record_is_quarantined_without_network_send(
    tmp_path: Path,
    secure_keyring: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    spool = _spool(tmp_path / "expired")
    with monkeypatch.context() as clock:
        clock.setattr("ctowerctl.spool.interface.datetime", _PastDateTime)
        spool.enqueue(_command())
    executor = _Accepting()

    report = spool.drain(executor)

    assert report.reason_code == "expired"
    assert report.quarantined == 1
    assert executor.calls == 0


class _Rejecting:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        del command
        return ReplayResponse(status_code=403, problem_code="unauthorized")


def _spool(state: Path) -> Spool:
    return Spool.for_origin("https://filesystem.example/api", SpoolConfig(state_path=state))


def _command(body: _JsonObject | None = None) -> SpoolCommand:
    return SpoolCommand(
        operation_id="createTicket",
        command_id=uuid4(),
        request_body=body or {"title": "filesystem"},
    )


def _root(state: Path) -> Path:
    origins = tuple((state / "spool" / "v1").iterdir())
    assert len(origins) == 1
    return origins[0]
