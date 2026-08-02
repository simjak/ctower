"""Pure public-Interface evidence for the encrypted CLI spool foundation."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ctowerctl.spool import (
    ReplayResponse,
    Spool,
    SpoolCommand,
    SpoolConfig,
    SpoolError,
    SpoolState,
)

__all__: tuple[str, ...] = ()

type _JsonScalar = str | int | float | bool | None
type _JsonValue = _JsonScalar | list[_JsonValue] | dict[str, _JsonValue]
type _JsonObject = dict[str, _JsonValue]

_TWO_COMMANDS = 2
_CREDENTIAL = "synthetic-foundation-identity"


class _MemoryBackend:
    priority = 1.0

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


_MemoryBackend.__module__ = "keyring.backends.SecretService"
_MemoryBackend.__name__ = "Keyring"


@pytest.fixture
def secure_keyring(monkeypatch: pytest.MonkeyPatch) -> _MemoryBackend:
    backend = _MemoryBackend()
    _install_keyring(monkeypatch, backend)
    return backend


@dataclass
class _Executor:
    response: ReplayResponse | BaseException
    calls: list[SpoolCommand] = field(default_factory=list)

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        self.calls.append(command)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class _Accepting:
    def __init__(self, response_body: _JsonObject | None = None) -> None:
        self.calls: list[SpoolCommand] = []
        self._body = response_body or {"result": "stored"}

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        self.calls.append(command)
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
            response=self._body,
            event_ids=("event-1",),
            acceptance_position="record:1",
        )


def test_durable_enqueue_is_idempotent_encrypted_and_redacted(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    command_id = uuid4()
    corpus = "private-title-comment-evidence-bundle-938c"
    command = _command(command_id, {"title": corpus, "comment": corpus, "evidence": [corpus]})
    spool = _spool(state)

    first = spool.enqueue(command)
    second = spool.enqueue(command)

    assert first == second
    assert first.state is SpoolState.PENDING
    assert spool.status().pending_count == 1
    assert corpus not in json.dumps(first.model_dump(mode="json"), sort_keys=True)
    assert b"https://example.test" not in _all_spool_bytes(state)
    assert corpus.encode() not in _all_spool_bytes(state)
    with pytest.raises(SpoolError, match="different request") as conflict:
        spool.enqueue(_command(command_id, {"title": "different"}))
    assert conflict.value.code == "command_id_conflict"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (ReplayResponse(status_code=429), "temporary_server_response"),
        (ReplayResponse(status_code=503), "temporary_server_response"),
        (
            ReplayResponse(
                status_code=200,
                command_id=UUID("00000000-0000-0000-0000-000000000001"),
                durability_state="accepted",
                response={},
            ),
            "mismatched_success",
        ),
        (
            ReplayResponse(
                status_code=200,
                command_id=None,
                durability_state=None,
                response={},
            ),
            "mismatched_success",
        ),
    ],
)
def test_ambiguous_or_temporary_response_keeps_exact_pending_command(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
    response: ReplayResponse,
    reason: str,
) -> None:
    del secure_keyring
    command = _command(uuid4(), {"title": "pending"})
    spool = _spool(tmp_path / reason)
    entry = spool.enqueue(command)
    executor = _Executor(response)

    report = spool.drain(executor)

    assert report.reason_code == reason
    assert report.remaining_pending == 1
    assert spool.list_entries()[0].sequence == entry.sequence
    assert spool.list_entries()[0].command_id == command.command_id


def test_timeout_and_durability_pending_never_archive(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    command = _command(uuid4(), {"title": "retry"})
    timeout_spool = _spool(tmp_path / "timeout")
    timeout_spool.enqueue(command)
    assert timeout_spool.drain(_Executor(TimeoutError())).remaining_pending == 1
    pending_spool = _spool(tmp_path / "pending")
    pending_spool.enqueue(command)
    response = ReplayResponse(
        status_code=200,
        command_id=command.command_id,
        durability_state="durability_pending",
        response={"state": "not-accepted"},
    )
    assert pending_spool.drain(_Executor(response)).remaining_pending == 1
    assert pending_spool.status().accepted_count == 0


def test_exact_acceptance_archives_only_after_durable_receipt(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    command = _command(uuid4(), {"title": "accept"})
    spool = _spool(state)
    spool.enqueue(command)
    response_corpus = "raw-response-private-45ef"

    report = spool.drain(_Accepting({"message": response_corpus}))

    assert report.accepted == 1
    assert spool.status().accepted_count == 1
    assert spool.list_entries()[0].state is SpoolState.ACCEPTED_ARCHIVE
    assert response_corpus.encode() not in _all_spool_bytes(state)
    assert spool.doctor().healthy


def test_permanent_rejection_is_ordering_barrier_with_retry_and_discard(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    spool = _spool(tmp_path / "state")
    first = spool.enqueue(_command(uuid4(), {"title": "first"}))
    rejected = ReplayResponse(
        status_code=422,
        problem_code="schema_rejected",
        response={"detail": "private detail"},
    )
    assert spool.drain(_Executor(rejected)).quarantined == 1
    assert spool.list_entries()[0].reason_code == "permanent_server_rejection"
    second = spool.enqueue(_command(uuid4(), {"title": "second"}))
    blocked_executor = _Accepting()
    blocked = spool.drain(blocked_executor)
    assert blocked.barrier_sequence == first.sequence
    assert not blocked_executor.calls

    retried = spool.retry(first.sequence or 0, "schema upgraded")
    assert retried.command_id == first.command_id
    accepting = _Accepting()
    assert spool.drain(accepting).accepted == _TWO_COMMANDS
    assert [item.command_id for item in accepting.calls] == [first.command_id, second.command_id]

    discard_spool = _spool(tmp_path / "discard")
    discarded = discard_spool.enqueue(_command(uuid4(), {"title": "discard"}))
    discard_spool.drain(_Executor(rejected))
    discard_spool.discard(discarded.sequence or 0, "operator chose replacement")
    assert discard_spool.list_entries() == ()
    assert tuple(
        _origin_root(tmp_path / "discard").joinpath("quarantine").glob("*.disposition.rec")
    )


def test_consecutive_discard_tombstones_bridge_chain_and_missing_or_forged_refuse(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    first = spool.enqueue(_command(uuid4(), {"title": "first"}))
    second = spool.enqueue(_command(uuid4(), {"title": "second"}))
    rejected = ReplayResponse(status_code=422, problem_code="schema_rejected")

    assert spool.drain(_Executor(rejected)).barrier_sequence == first.sequence
    spool.discard(first.sequence or 0, "replace first")
    assert spool.drain(_Executor(rejected)).barrier_sequence == second.sequence
    spool.discard(second.sequence or 0, "replace second")

    assert spool.list_entries() == ()
    assert spool.doctor().healthy
    third = spool.enqueue(_command(uuid4(), {"title": "third"}))
    assert spool.drain(_Accepting()).accepted == 1
    assert third.sequence is not None
    assert spool.doctor().healthy

    missing = tmp_path / "missing"
    forged = tmp_path / "forged"
    shutil.copytree(state, missing)
    shutil.copytree(state, forged)
    missing_tombstone = sorted(
        _origin_root(missing).joinpath("quarantine").glob("*.disposition.rec")
    )[0]
    missing_tombstone.unlink()
    assert _unbound_spool(missing).status().reason_codes == ("chain_integrity",)

    forged_tombstone = sorted(
        _origin_root(forged).joinpath("quarantine").glob("*.disposition.rec")
    )[0]
    forged_bytes = bytearray(forged_tombstone.read_bytes())
    forged_bytes[len(forged_bytes) // 2] ^= 1
    forged_tombstone.write_bytes(forged_bytes)
    assert _unbound_spool(forged).status().reason_codes == ("chain_integrity",)


def test_replay_credential_identity_mismatch_is_zero_send_and_recoverable(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    original = _spool(state)
    command = original.enqueue(_command(uuid4(), {"title": "identity-bound"}))
    rotated = _unbound_spool(state).bind_credential("synthetic-rotated-identity")
    executor = _Accepting()

    refused = rotated.drain(executor)

    assert refused.attempted == 0
    assert refused.quarantined == 1
    assert refused.reason_code == "credential_identity_mismatch"
    assert executor.calls == []
    assert original.list_entries()[0].reason_code == "credential_identity_mismatch"
    original.retry(command.sequence or 0, "original identity restored")
    accepted = _Accepting()
    assert original.drain(accepted).accepted == 1
    assert [item.command_id for item in accepted.calls] == [command.command_id]
    corpus = _all_spool_bytes(state)
    assert _CREDENTIAL.encode() not in corpus
    assert b"synthetic-rotated-identity" not in corpus


def test_missing_or_unapproved_keyring_fails_state_unknown_without_moving_ciphertext(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command(uuid4(), {"title": "keep"}))
    pending = tuple(_origin_root(state).joinpath("pending").glob("*.rec"))
    monkeypatch.setitem(sys.modules, "keyring", types.ModuleType("keyring"))

    status = spool.status()

    assert status.health == "state_unknown"
    assert not status.keyring_available
    assert tuple(_origin_root(state).joinpath("pending").glob("*.rec")) == pending
    assert not tuple(_origin_root(state).joinpath("quarantine").glob("*.rec"))


def test_bootstrap_and_reusable_authority_fields_are_refused_before_disk(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    with pytest.raises(ValidationError):
        _command(uuid4(), {"authorization": "synthetic"})
    with pytest.raises(ValidationError):
        SpoolCommand(
            operation_id="bootstrapFirstTenant",
            command_id=uuid4(),
            request_body={"tenant": "example"},
        )
    assert not (tmp_path / "state").exists()


def test_bounded_count_and_record_size_refuse_before_another_append(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    config = SpoolConfig(
        state_path=state,
        max_live_commands=1,
        max_scan_entries=100,
        max_command_bytes=64 * 1024,
        max_live_bytes=1024 * 1024,
    )
    spool = Spool.for_origin("https://example.test", config).bind_credential(_CREDENTIAL)
    spool.enqueue(_command(uuid4(), {"title": "one"}))
    with pytest.raises(SpoolError) as count_error:
        spool.enqueue(_command(uuid4(), {"title": "two"}))
    assert count_error.value.code == "capacity_count"
    large = Spool.for_origin("https://large.example", config).bind_credential(_CREDENTIAL)
    with pytest.raises(SpoolError) as size_error:
        large.enqueue(_command(uuid4(), {"body": "x" * (64 * 1024)}))
    assert size_error.value.code == "command_too_large"
    assert large.status().pending_count == 0


def _install_keyring(monkeypatch: pytest.MonkeyPatch, backend: object) -> None:
    module = types.ModuleType("keyring")
    module.__dict__["get_keyring"] = lambda: backend
    monkeypatch.setitem(sys.modules, "keyring", module)


def _spool(state: Path) -> Spool:
    return _unbound_spool(state).bind_credential(_CREDENTIAL)


def _unbound_spool(state: Path) -> Spool:
    return Spool.for_origin(
        "https://example.test/api",
        SpoolConfig(state_path=state),
    )


def _command(command_id: UUID, body: _JsonObject) -> SpoolCommand:
    return SpoolCommand(
        operation_id="createTicket",
        path_parameters={"tenant": "tenant-a"},
        request_body=body,
        command_id=command_id,
    )


def _origin_root(state: Path) -> Path:
    origins = tuple((state / "spool" / "v1").iterdir())
    assert len(origins) == 1
    return origins[0]


def _all_spool_bytes(state: Path) -> bytes:
    return b"".join(path.read_bytes() for path in _origin_root(state).rglob("*") if path.is_file())


def test_owner_only_modes_cover_every_created_directory_and_file(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command(uuid4(), {"title": "modes"}))

    root = _origin_root(state)
    for path in (state, state / "spool", state / "spool" / "v1", root, *root.rglob("*")):
        details = path.stat()
        assert details.st_uid == os.geteuid()
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(details.st_mode) == expected
        if path.is_file():
            assert details.st_nlink == 1
