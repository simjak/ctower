"""Fixed synthetic handler sequencing over the generated public client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

import pytest

from ctower_api.synthetic_handler import (
    SyntheticFourStageHandler,
    SyntheticPolicyPins,
    SyntheticRetryError,
)
from ctower_client import CtowerClient, DurabilityState
from ctower_kernel.runtime import FixedOperationAttempt, FixedOperationJob

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + "a" * 64


@dataclass(frozen=True, slots=True)
class _Ticket:
    ticket_id: UUID


@dataclass(frozen=True, slots=True)
class _Receipt:
    durability_state: DurabilityState
    lifecycle_facts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _TicketReceipt:
    durability_state: DurabilityState
    ticket: _Ticket


class _TransitionRequest(Protocol):
    destination_stage: str


class _Client:
    def __init__(
        self,
        calls: list[tuple[str, UUID]],
        ticket_id: UUID,
        *,
        pending_method: str | None = None,
    ) -> None:
        self.calls = calls
        self.ticket_id = ticket_id
        self.pending_method = pending_method

    def create_ticket(self, _request: object, *, command_id: UUID) -> _TicketReceipt:
        self._record("capture", command_id)
        return _TicketReceipt(self._state("capture"), _Ticket(self.ticket_id))

    def start_ticket_workflow(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt("start", command_id)

    def apply_ticket_intent(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt("admit", command_id)

    def transition_workflow(
        self, _ticket_id: UUID, request: _TransitionRequest, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt(request.destination_stage, command_id)

    def freeze_proof_criteria(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt("freeze", command_id)

    def record_proof_evidence(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt("evidence", command_id)

    def record_proof_verdict(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        return self._receipt("verdict", command_id)

    def resolve_close_workflow(
        self, _ticket_id: UUID, _request: object, *, command_id: UUID
    ) -> _Receipt:
        self._record("resolve-close", command_id)
        return _Receipt(self._state("resolve-close"), ("resolved", "closed"))

    def _receipt(self, method: str, command_id: UUID) -> _Receipt:
        self._record(method, command_id)
        return _Receipt(self._state(method))

    def _record(self, method: str, command_id: UUID) -> None:
        self.calls.append((method, command_id))

    def _state(self, method: str) -> DurabilityState:
        if method == self.pending_method:
            return DurabilityState.DURABILITY_PENDING
        return DurabilityState.ACCEPTED


def test_fixed_handler_executes_exact_public_sequence_with_stable_identities() -> None:
    calls: list[tuple[str, UUID]] = []
    ticket_id = uuid4()
    author = _Client(calls, ticket_id)
    reviewer = _Client(calls, ticket_id)
    handler = _handler(author, reviewer)
    attempt = _attempt()

    completion = handler.execute(attempt)
    first = tuple(calls)
    handler.execute(attempt)
    second = tuple(calls[len(first) :])

    assert tuple(name for name, _command_id in first) == (
        "capture",
        "start",
        "admit",
        "frame",
        "freeze",
        "verify",
        "evidence",
        "verdict",
        "close",
        "resolve-close",
    )
    assert second == first
    assert completion.succeeded is True
    assert completion.ticket_id == ticket_id
    assert completion.lifecycle_facts == ("resolved", "closed")


def test_fixed_handler_retries_a_pending_semantic_step_without_changing_identity() -> None:
    calls: list[tuple[str, UUID]] = []
    ticket_id = uuid4()
    author = _Client(calls, ticket_id, pending_method="capture")
    handler = _handler(author, _Client(calls, ticket_id))
    attempt = _attempt()

    with pytest.raises(SyntheticRetryError, match="awaits accepted"):
        handler.execute(attempt)
    pending_command = calls[0][1]
    author.pending_method = None

    handler.execute(attempt)

    assert calls[1] == ("capture", pending_command)


def _handler(author: _Client, reviewer: _Client) -> SyntheticFourStageHandler:
    pins = SyntheticPolicyPins(_DIGEST, _DIGEST, _DIGEST, _DIGEST)
    return SyntheticFourStageHandler(
        cast(CtowerClient, author),
        cast(CtowerClient, reviewer),
        uuid4(),
        pins,
    )


def _attempt() -> FixedOperationAttempt:
    now = datetime.now(UTC)
    job = FixedOperationJob(uuid4(), uuid4(), uuid4(), "synthetic_four_stage", 60, (), now)
    return FixedOperationAttempt(uuid4(), job, 1, uuid4(), "test-worker", now, now + timedelta(1))
