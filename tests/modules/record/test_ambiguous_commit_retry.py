"""Bounded backoff coverage for ambiguous-commit recovery (gh#88, O10)."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg
import pytest

import ctower_kernel.record.transaction as transaction_module
from ctower_kernel.record.transaction import (
    AmbiguousCommitExhaustedError,
    RecordTransaction,
    recover_ambiguous_commit,
)

__all__: tuple[str, ...] = ()

_PRINCIPAL_ID = UUID("00000000-0000-4000-8000-000000000001")
_COMMAND_ID = UUID("00000000-0000-4000-8000-000000000002")
_REQUEST_DIGEST = bytes(32)
_MAXIMUM_ATTEMPTS = 3
_SUCCEEDS_ON_SECOND_ATTEMPT = 2


class _MaximumJitter:
    @staticmethod
    def uniform(_lower: float, upper: float) -> float:
        return upper


class _Result:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class _PolicyConnection:
    """Fake authority connection recording every statement it is given."""

    def __init__(self, mode: str, commit_deadline_ms: int) -> None:
        self._policy = {"mode": mode, "commit_deadline_ms": commit_deadline_ms}
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> _Result:
        self.calls.append((query, params))
        if "durability_policy_state" in query:
            return _Result(self._policy)
        return _Result(None)


def _as_connection(connection: object) -> psycopg.Connection[dict[str, object]]:
    return cast(psycopg.Connection[dict[str, object]], connection)


def test_recover_ambiguous_commit_retries_transient_failures_with_capped_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def transient_then_success() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise psycopg.errors.QueryCanceled("statement canceled while waiting on commit")
        if attempts < _MAXIMUM_ATTEMPTS:
            raise psycopg.OperationalError("connection lost after commit was sent")
        return "committed"

    monkeypatch.setattr(transaction_module, "_RANDOM", _MaximumJitter())
    monkeypatch.setattr(
        "ctower_kernel.record.transaction.time.sleep",
        sleeps.append,
    )

    outcome = recover_ambiguous_commit(transient_then_success)

    assert outcome == "committed"
    assert attempts == _MAXIMUM_ATTEMPTS
    assert sleeps == [0.05, 0.1]


def test_recover_ambiguous_commit_permanent_failure_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def permanent_failure() -> str:
        nonlocal attempts
        attempts += 1
        raise psycopg.errors.UniqueViolation("duplicate key")

    monkeypatch.setattr(
        "ctower_kernel.record.transaction.time.sleep",
        sleeps.append,
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        recover_ambiguous_commit(permanent_failure)

    assert attempts == 1
    assert sleeps == []


def test_recover_ambiguous_commit_exhaustion_is_typed_and_attributable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[psycopg.OperationalError] = []
    sleeps: list[float] = []

    def always_ambiguous() -> str:
        failure = psycopg.OperationalError("connection lost after commit was sent")
        failures.append(failure)
        raise failure

    monkeypatch.setattr(transaction_module, "_RANDOM", _MaximumJitter())
    monkeypatch.setattr(
        "ctower_kernel.record.transaction.time.sleep",
        sleeps.append,
    )

    with pytest.raises(AmbiguousCommitExhaustedError) as raised:
        recover_ambiguous_commit(always_ambiguous)

    assert len(failures) == _MAXIMUM_ATTEMPTS
    assert raised.value.attempt_count == _MAXIMUM_ATTEMPTS
    assert raised.value.elapsed_seconds >= 0
    assert raised.value.last_failure is failures[-1]
    assert sleeps == [0.05, 0.1]


def test_recover_ambiguous_commit_reruns_the_full_idempotent_operation_every_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every attempt re-enters the caller's reserve-check, never just the raw write.

    This is the replay-safety property the retry bound leans on: `operation` is the
    caller's whole reserve-then-mutate closure (see e.g. `proof.postgres.mutate_proof`),
    so a retry can only ever observe a prior commit through its idempotency key -- it
    never skips straight to a bare re-write. Counting invocations here stands in for
    that structural guarantee at the unit level.
    """

    reserve_checks = 0
    monkeypatch.setattr(
        "ctower_kernel.record.transaction.time.sleep",
        lambda _seconds: None,
    )

    def reserve_then_mutate() -> str:
        nonlocal reserve_checks
        reserve_checks += 1
        if reserve_checks < _SUCCEEDS_ON_SECOND_ATTEMPT:
            raise psycopg.OperationalError("connection lost after commit was sent")
        return "committed"

    outcome = recover_ambiguous_commit(reserve_then_mutate)

    assert outcome == "committed"
    assert reserve_checks == _SUCCEEDS_ON_SECOND_ATTEMPT


def test_reserve_caps_ordinary_mode_statement_timeout() -> None:
    connection = _PolicyConnection("pending_only", 1500)
    transaction = RecordTransaction(_as_connection(connection))

    result = transaction.reserve(_PRINCIPAL_ID, _COMMAND_ID, _REQUEST_DIGEST)

    assert result is None
    timeout_calls = [call for call in connection.calls if "statement_timeout" in call[0]]
    assert timeout_calls == [
        ("SELECT set_config('statement_timeout', %s, true)", ("1500ms",)),
    ]
    assert not any("synchronous_commit" in call[0] for call in connection.calls)


def test_reserve_arms_remote_apply_deadline_in_cutover_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    armed: list[int] = []
    monkeypatch.setattr(
        transaction_module,
        "arm_remote_apply_deadline",
        lambda _connection, milliseconds: armed.append(milliseconds),
    )
    connection = _PolicyConnection("cutover_rpo0", 2500)
    transaction = RecordTransaction(_as_connection(connection))

    transaction.reserve(_PRINCIPAL_ID, _COMMAND_ID, _REQUEST_DIGEST)

    timeout_calls = [call for call in connection.calls if "statement_timeout" in call[0]]
    assert timeout_calls == [
        ("SELECT set_config('statement_timeout', %s, true)", ("2500ms",)),
    ]
    assert any("synchronous_commit" in call[0] for call in connection.calls)
    assert armed == [2500]
