"""Fail-closed policy and adapter edge evidence for the encrypted CLI spool."""

from __future__ import annotations

import base64
import importlib
import sys
import types
from collections.abc import Callable
from functools import partial
from pathlib import Path
from uuid import uuid4

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

_TWO_COMMANDS = 2
_CREDENTIAL = "synthetic-policy-identity"


class _Backend:
    priority = 1.0

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        if self.mode == "load_raise":
            raise RuntimeError("synthetic locked keyring")
        if self.mode == "load_missing":
            return None
        if self.mode == "load_invalid":
            return "not-base64"
        if self.mode == "load_short":
            return base64.b64encode(b"short").decode("ascii")
        if self.mode == "existing":
            return base64.b64encode(b"x" * 32).decode("ascii")
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.mode == "set_raise":
            raise RuntimeError("synthetic refusal")
        if self.mode == "missing_after_set":
            return
        if self.mode == "invalid_after_set":
            self.values[(service, username)] = "not-base64"
            return
        if self.mode == "short_after_set":
            self.values[(service, username)] = base64.b64encode(b"short").decode("ascii")
            return
        if self.mode == "mismatch_after_set":
            self.values[(service, username)] = base64.b64encode(b"y" * 32).decode("ascii")
            return
        self.values[(service, username)] = password


_Backend.__module__ = "keyring.backends.SecretService"
_Backend.__name__ = "Keyring"


class _UnapprovedBackend(_Backend):
    pass


class _Accepting:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
            response={"stored": True},
        )


class _Rejecting:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        del command
        return ReplayResponse(status_code=422, problem_code="invalid_request")


class _SecretResponse:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        return ReplayResponse(
            status_code=200,
            command_id=command.command_id,
            durability_state="accepted",
            response={"authorization": "synthetic authority"},
        )


class _EmptyAcceptedResponse:
    def execute(self, command: SpoolCommand) -> ReplayResponse:
        return ReplayResponse(
            status_code=204,
            command_id=command.command_id,
            durability_state="accepted",
            response=None,
        )


@pytest.mark.parametrize(
    "origin",
    [
        "relative/path",
        "ftp://example.test",
        "https://user@example.test",
        "https://example.test?query=1",
        "https://example.test#fragment",
        "https://example.test:99999",
        "http://example.test",
        "https://example.test/a/../b",
        "https://example.test/%ZZ",
        "https://example.test/%FF",
        "https://[invalid",
    ],
)
def test_origin_policy_rejects_noncanonical_or_unsafe_authorities(
    tmp_path: Path,
    origin: str,
) -> None:
    with pytest.raises(SpoolError) as failure:
        Spool.for_origin(origin, SpoolConfig(state_path=tmp_path))
    assert failure.value.code == "invalid_origin"


def test_origin_policy_accepts_only_loopback_cleartext_and_bounded_config(tmp_path: Path) -> None:
    for origin in ("http://localhost", "http://127.0.0.1:8080", "http://[::1]/api"):
        Spool.for_origin(origin, SpoolConfig(state_path=tmp_path))
    with pytest.raises(ValidationError):
        SpoolConfig(max_command_bytes=1024 * 1024, max_live_bytes=1024)
    with pytest.raises(ValidationError):
        SpoolConfig(max_live_commands=101, max_scan_entries=100)


def test_missing_platform_state_resolver_is_a_stable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = importlib.import_module

    def unavailable(name: str) -> types.ModuleType:
        if name == "platformdirs":
            raise ImportError("synthetic missing dependency")
        return original(name)

    monkeypatch.setattr(
        "ctowerctl.spool.interface.importlib.import_module",
        unavailable,
    )
    with pytest.raises(SpoolError) as failure:
        Spool.for_origin("https://example.test")
    assert failure.value.code == "platform_state_unavailable"


def test_doctor_filters_limits_dispositions_and_empty_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _Backend()
    _install_keyring(monkeypatch, backend)
    unbound = Spool.for_origin(
        "https://policy.example/api",
        SpoolConfig(state_path=tmp_path),
    )
    assert unbound.doctor().state == "uninitialized"
    spool = unbound.bind_credential(_CREDENTIAL)
    first = spool.enqueue(_command("first"))
    spool.drain(_Rejecting())
    spool.enqueue(_command("second"))

    assert len(spool.list_entries(SpoolState.QUARANTINE)) == 1
    assert len(spool.list_entries(SpoolState.PENDING)) == 1
    for limit in (0, 20_001):
        with pytest.raises(SpoolError) as scan:
            spool.list_entries(limit=limit)
        assert scan.value.code == "scan_limit"
    for reason in ("", "x" * 501):
        with pytest.raises(SpoolError) as invalid_reason:
            spool.retry(first.sequence or 0, reason)
        assert invalid_reason.value.code == "invalid_disposition"
    with pytest.raises(SpoolError) as missing:
        spool.retry(999, "not quarantined")
    assert missing.value.code == "invalid_disposition"
    assert _spool(tmp_path / "empty").compact() == 0


def test_doctor_reports_tightened_capacity_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_keyring(monkeypatch, _Backend())
    spool = _spool(tmp_path)
    spool.enqueue(_command("first"))
    spool.enqueue(_command("second"))
    tightened = Spool.for_origin(
        "https://policy.example/api",
        SpoolConfig(
            state_path=tmp_path,
            max_live_commands=1,
            max_scan_entries=100,
        ),
    )

    report = tightened.doctor()

    assert not report.healthy
    assert report.state == "degraded"
    assert spool.status().pending_count == _TWO_COMMANDS


def test_secret_response_and_recent_acceptance_remain_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_keyring(monkeypatch, _Backend())
    secret_spool = _spool(tmp_path / "secret")
    secret_spool.enqueue(_command("secret-response"))
    with pytest.raises(SpoolError) as secret:
        secret_spool.drain(_SecretResponse())
    assert secret.value.code == "secret_material"
    assert secret_spool.status().pending_count == 1

    recent = _spool(tmp_path / "recent")
    recent.enqueue(_command("recent"))
    recent.drain(_Accepting())
    assert recent.compact() == 0

    empty_response = _spool(tmp_path / "empty-response")
    empty_response.enqueue(_command("no-content"))
    assert empty_response.drain(_EmptyAcceptedResponse()).accepted == 1
    assert empty_response.status().accepted_count == 1


def test_validation_errors_hide_forbidden_request_content() -> None:
    corpus = "private-input-value-91af"
    with pytest.raises(ValidationError) as failure:
        SpoolCommand(
            operation_id="createTicket",
            command_id=uuid4(),
            request_body={"nested": {"token": corpus}},
        )
    assert corpus not in str(failure.value)


@pytest.mark.parametrize(
    "mode",
    [
        "existing",
        "load_raise",
        "set_raise",
        "missing_after_set",
        "invalid_after_set",
        "short_after_set",
        "mismatch_after_set",
    ],
)
def test_key_creation_anomalies_fail_before_a_command_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _install_keyring(monkeypatch, _Backend(mode))
    with pytest.raises(SpoolError) as failure:
        _spool(tmp_path).enqueue(_command(mode))
    assert failure.value.code == "keyring_unavailable"
    spool = Spool.for_origin(
        "https://policy.example/api",
        SpoolConfig(state_path=tmp_path),
    )
    assert spool.status().pending_count is None


@pytest.mark.parametrize("priority", (0.0, -1.0))
def test_unapproved_or_disabled_backend_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    priority: float,
) -> None:
    backend = _Backend()
    backend.priority = priority
    _install_keyring(monkeypatch, backend)
    with pytest.raises(SpoolError) as failure:
        _spool(tmp_path).enqueue(_command("disabled"))
    assert failure.value.code == "keyring_unavailable"

    _install_keyring(monkeypatch, _UnapprovedBackend())
    with pytest.raises(SpoolError) as unapproved:
        _spool(tmp_path / "unapproved").enqueue(_command("unapproved"))
    assert unapproved.value.code == "keyring_unavailable"


@pytest.mark.parametrize(
    "mode",
    ["load_raise", "load_missing", "load_invalid", "load_short"],
)
def test_key_load_anomalies_never_guess_encrypted_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    backend = _Backend()
    _install_keyring(monkeypatch, backend)
    spool = _spool(tmp_path)
    spool.enqueue(_command("preserved"))
    backend.mode = mode

    status = spool.status()

    assert status.health == "state_unknown"
    assert not status.keyring_available
    assert status.pending_count is None
    assert spool.doctor().state == "state_unknown"


def test_keyring_failure_is_redacted_across_mutating_and_listing_apis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _Backend()
    _install_keyring(monkeypatch, backend)
    spool = _spool(tmp_path)
    spool.enqueue(_command("preserved"))
    backend.mode = "load_missing"

    operations: tuple[Callable[[], object], ...] = (
        spool.list_entries,
        partial(spool.drain, _Accepting()),
        spool.compact,
    )
    for operation in operations:
        with pytest.raises(SpoolError) as failure:
            operation()
        assert failure.value.code == "keyring_unavailable"


def _install_keyring(monkeypatch: pytest.MonkeyPatch, backend: object) -> None:
    module = types.ModuleType("keyring")
    module.__dict__["get_keyring"] = lambda: backend
    monkeypatch.setitem(sys.modules, "keyring", module)


def _spool(state: Path) -> Spool:
    return Spool.for_origin(
        "https://policy.example/api",
        SpoolConfig(state_path=state),
    ).bind_credential(_CREDENTIAL)


def _command(title: str) -> SpoolCommand:
    return SpoolCommand(
        operation_id="createTicket",
        command_id=uuid4(),
        request_body={"title": title},
    )
