"""Public-Interface evidence that a durable refusal keeps a name and nothing else."""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ctowerctl.spool import (
    ReplayResponse,
    ServerRefusal,
    Spool,
    SpoolCommand,
    SpoolConfig,
    SpoolEntry,
    SpoolState,
    server_refusal,
)

__all__: tuple[str, ...] = ()

type _JsonScalar = str | int | float | bool | None
type _JsonValue = _JsonScalar | list[_JsonValue] | dict[str, _JsonValue]
type _JsonObject = dict[str, _JsonValue]

_CREDENTIAL = "synthetic-refusal-identity"
_PII_MARKER = "jane.doe+ct180@example.invalid"
_BEARER_MARKER = "Bearer synthetic-refusal-probe-not-a-credential"
_PII_SLUG = "jane_doe_ct180_example_invalid"
_BEARER_SLUG = "bearer_synthetic_refusal_probe_not_a_credential"
_UNRECOGNIZED = "unrecognized_refusal"


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
    module = types.ModuleType("keyring")
    module.__dict__["get_keyring"] = lambda: backend
    monkeypatch.setitem(sys.modules, "keyring", module)
    return backend


class _RelaxedRefusal(ServerRefusal):
    """A caller's own refusal class, widened back to arbitrary text."""

    name: str


@dataclass
class _Executor:
    response: ReplayResponse
    calls: list[SpoolCommand] = field(default_factory=list)

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        self.calls.append(command)
        return self.response


class _Accepting:
    def __init__(self) -> None:
        self.calls: list[SpoolCommand] = []

    def execute(self, command: SpoolCommand) -> ReplayResponse:
        self.calls.append(command)
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
            response={"result": "stored"},
            event_ids=("event-1",),
            acceptance_position="record:1",
        )


def test_server_refusal_is_named_in_the_listing_while_local_refusal_names_no_server(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    del secure_keyring
    refusal = server_refusal(403, "unauthorized")
    rejected = _spool(tmp_path / "rejected")
    rejected.enqueue(_command(uuid4(), {"title": "refused"}))

    report = rejected.drain(_Executor(_refused(refusal)))

    assert report.quarantined == 1
    named = _unbound_spool(tmp_path / "rejected").list_entries(SpoolState.QUARANTINE)[0]
    assert named.reason_code == "permanent_server_rejection"
    assert named.server_refusal == ServerRefusal(status=403, name="unauthorized")
    local = _spool(tmp_path / "local")
    local.enqueue(_command(uuid4(), {"title": "identity-bound"}))
    rotated = _unbound_spool(tmp_path / "local").bind_credential("synthetic-rotated-identity")

    assert rotated.drain(_Accepting()).reason_code == "credential_identity_mismatch"
    unnamed = _unbound_spool(tmp_path / "local").list_entries(SpoolState.QUARANTINE)[0]
    assert unnamed.reason_code == "credential_identity_mismatch"
    assert unnamed.server_refusal is None


def test_only_an_authored_name_or_the_content_free_sentinel_can_exist(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    """Response prose has no durable field to live in, and no slug to hide in."""

    del secure_keyring
    assert server_refusal(403, "tenant-scope-denied").name == "tenant_scope_denied"
    assert server_refusal(403, f"Refused for {_PII_MARKER}").name == _UNRECOGNIZED
    assert server_refusal(500, f"{_BEARER_MARKER} presented").name == _UNRECOGNIZED
    assert server_refusal(500, "!!").name == _UNRECOGNIZED
    for rejected in (f"unauthorized: {_BEARER_MARKER}", f"{_UNRECOGNIZED}:jane_doe", "unnamed"):
        with pytest.raises(ValidationError):
            ServerRefusal(status=403, name=rejected)

    spool = _spool(tmp_path / "state")
    spool.enqueue(_command(uuid4(), {"title": "refused"}))
    spool.drain(_Executor(_refused(server_refusal(403, "unauthorized"))))

    listed = spool.list_entries(SpoolState.QUARANTINE)[0]
    corpus = _all_spool_bytes(tmp_path / "state")
    assert listed.server_refusal == ServerRefusal(status=403, name="unauthorized")
    assert _PII_MARKER.encode() not in corpus
    assert _BEARER_MARKER.encode() not in corpus


def test_relaxed_refusal_subclass_cannot_poison_the_spool_through_a_caller_executor(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    """A caller owns its executor, so it owns the refusal class the receipt must not trust."""

    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command(uuid4(), {"title": "refused"}))
    relaxed = _RelaxedRefusal(status=403, name=f"{_PII_MARKER} {_BEARER_MARKER}")

    assert relaxed.name == f"{_PII_MARKER} {_BEARER_MARKER}"
    carried = ReplayResponse(status_code=403, refusal=relaxed).refusal
    assert type(carried) is ServerRefusal
    assert carried == ServerRefusal(status=403, name=_UNRECOGNIZED)

    report = spool.drain(_Executor(_refused_by(relaxed)))

    assert report.quarantined == 1
    reopened = _unbound_spool(state)
    listed = reopened.list_entries(SpoolState.QUARANTINE)
    assert reopened.doctor().healthy
    assert reopened.status().reason_codes == ("permanent_server_rejection",)
    assert [item.server_refusal for item in listed] == [
        ServerRefusal(status=403, name=_UNRECOGNIZED)
    ]
    _assert_no_marker_survives(listed, _all_spool_bytes(state))


def test_unvalidated_replay_response_still_cannot_seal_a_refusal_into_a_receipt(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    """The receipt re-derives the name even when no executor response was ever validated."""

    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command(uuid4(), {"title": "refused"}))
    relaxed = _RelaxedRefusal(status=403, name=f"{_PII_MARKER} {_BEARER_MARKER}")
    unvalidated = ReplayResponse.model_construct(
        status_code=403,
        command_id=None,
        durability_state=None,
        response={"code": "unauthorized", "status": 403},
        event_ids=(),
        acceptance_position=None,
        problem_code="unauthorized",
        refusal=relaxed,
    )

    assert unvalidated.refusal is relaxed
    assert spool.drain(_Executor(unvalidated)).quarantined == 1

    reopened = _unbound_spool(state)
    listed = reopened.list_entries(SpoolState.QUARANTINE)
    assert reopened.doctor().healthy
    assert [item.server_refusal for item in listed] == [
        ServerRefusal(status=403, name=_UNRECOGNIZED)
    ]
    _assert_no_marker_survives(listed, _all_spool_bytes(state))


def test_public_spool_round_trip_cannot_persist_or_list_an_unknown_refusal_code(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    """The exported executor boundary is a caller's, so it must not carry text either."""

    del secure_keyring
    state = tmp_path / "state"
    spool = _spool(state)
    spool.enqueue(_command(uuid4(), {"title": "refused"}))
    hostile_code = f"refused-for-{_PII_MARKER}-presenting-{_BEARER_MARKER}"

    report = spool.drain(_Executor(_refused(server_refusal(403, hostile_code))))

    assert report.quarantined == 1
    listed = _unbound_spool(state).list_entries(SpoolState.QUARANTINE)
    assert listed[0].reason_code == "permanent_server_rejection"
    assert listed[0].server_refusal == ServerRefusal(status=403, name=_UNRECOGNIZED)
    _assert_no_marker_survives(listed, _all_spool_bytes(state))


def test_command_held_behind_a_quarantined_head_later_gets_its_own_refusal_name(
    tmp_path: Path,
    secure_keyring: _MemoryBackend,
) -> None:
    """The barrier must not blur two refusals into the head command's name."""

    del secure_keyring
    spool = _spool(tmp_path / "state")
    first = spool.enqueue(_command(uuid4(), {"title": "first"}))
    second = spool.enqueue(_command(uuid4(), {"title": "second"}))
    head_refusal = _Executor(_refused(server_refusal(403, "unauthorized")))

    assert spool.drain(head_refusal).barrier_sequence == first.sequence
    assert [item.command_id for item in head_refusal.calls] == [first.command_id]
    held = spool.list_entries()
    assert [item.server_refusal for item in held] == [
        ServerRefusal(status=403, name="unauthorized"),
        None,
    ]

    spool.discard(first.sequence or 0, "operator replaced the refused command")
    own_refusal = _Executor(_refused(server_refusal(409, "version-conflict")))

    assert spool.drain(own_refusal).quarantined == 1
    assert [item.command_id for item in own_refusal.calls] == [second.command_id]
    listed = spool.list_entries(SpoolState.QUARANTINE)
    assert [item.command_id for item in listed] == [second.command_id]
    assert listed[0].server_refusal == ServerRefusal(status=409, name="version_conflict")


def _spool(state: Path) -> Spool:
    return _unbound_spool(state).bind_credential(_CREDENTIAL)


def _unbound_spool(state: Path) -> Spool:
    return Spool.for_origin("https://example.test/api", SpoolConfig(state_path=state))


def _command(command_id: UUID, body: _JsonObject) -> SpoolCommand:
    return SpoolCommand(
        operation_id="createTicket",
        path_parameters={"tenant": "tenant-a"},
        request_body=body,
        command_id=command_id,
    )


def _refused(refusal: ServerRefusal) -> ReplayResponse:
    return ReplayResponse(
        status_code=refusal.status,
        problem_code=refusal.name,
        response={"code": refusal.name, "status": refusal.status},
        refusal=refusal,
    )


def _refused_by(refusal: ServerRefusal) -> ReplayResponse:
    """Build the response a caller's executor returns, without naming its refusal here."""

    return ReplayResponse(
        status_code=refusal.status,
        problem_code="unauthorized",
        response={"code": "unauthorized", "status": refusal.status},
        refusal=refusal,
    )


def _assert_no_marker_survives(entries: tuple[SpoolEntry, ...], corpus: bytes) -> None:
    rendered = json.dumps([item.model_dump(mode="json") for item in entries], sort_keys=True)
    for marker in (_PII_MARKER, _BEARER_MARKER, _PII_SLUG, _BEARER_SLUG):
        assert marker not in rendered
        assert marker.encode() not in corpus


def _all_spool_bytes(state: Path) -> bytes:
    origins = tuple((state / "spool" / "v1").iterdir())
    assert len(origins) == 1
    return b"".join(path.read_bytes() for path in origins[0].rglob("*") if path.is_file())
