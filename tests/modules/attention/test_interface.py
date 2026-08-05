"""Authenticated poison recovery commands through the public Attention Interface."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ctower_kernel.attention import (
    AppendFinding,
    Attention,
    AttentionFindingReceipt,
    FindingDisposition,
    FindingDispositionReceipt,
    PoisonDisposition,
    PoisonDispositionAction,
    PoisonDispositionReceipt,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem


class _Store:
    def __init__(self) -> None:
        self.commands: list[PoisonDisposition] = []

    def disposition(self, actor: Actor, command: PoisonDisposition) -> PoisonDispositionReceipt:
        self.commands.append(command)
        return PoisonDispositionReceipt(
            actor.tenant_id,
            actor.principal_id,
            command,
            datetime(2026, 7, 22, tzinfo=UTC),
        )

    def append_finding(
        self, actor: Actor, command: AppendFinding
    ) -> AttentionFindingReceipt | RecordProblem:
        raise NotImplementedError("unused by this poison-disposition test double")

    def record_finding_disposition(
        self, actor: Actor, command: FindingDisposition
    ) -> FindingDispositionReceipt | RecordProblem:
        raise NotImplementedError("unused by this poison-disposition test double")


def test_retry_and_tombstone_are_the_only_typed_recovery_actions() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    store = _Store()
    attention = Attention(store)

    for action in PoisonDispositionAction:
        command = _command(action)
        receipt = attention.disposition(actor, command)
        assert not isinstance(receipt, RecordProblem)
        assert receipt.command is command
        assert receipt.tenant_id == actor.tenant_id

    assert [item.action for item in store.commands] == [
        PoisonDispositionAction.RETRY,
        PoisonDispositionAction.TOMBSTONE,
    ]


def test_partition_keys_fail_closed_before_reaching_the_store() -> None:
    with pytest.raises(ValueError, match="partition keys"):
        _command(PoisonDispositionAction.RETRY, consumer_key="Board Projection")


def _command(
    action: PoisonDispositionAction, *, consumer_key: str = "board_projection"
) -> PoisonDisposition:
    return PoisonDisposition(
        client_command_id=uuid4(),
        consumer_key=consumer_key,
        topic="record.events",
        outbox_id=UUID("00000000-0000-4000-8000-000000000001"),
        action=action,
        reason="Operator reviewed the immutable poison evidence",
    )
