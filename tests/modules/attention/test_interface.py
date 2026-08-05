"""Authenticated poison recovery commands through the public Attention Interface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.attention import (
    AppendFinding,
    Attention,
    AttentionFindingReceipt,
    FindingDisposition,
    FindingDispositionOutcome,
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


def test_append_finding_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _finding(subject_ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="kind is outside"):
        _finding(kind_key="Not Valid")
    with pytest.raises(ValueError, match="reason code is outside"):
        _finding(reason_code="Not Valid")
    with pytest.raises(ValueError, match="owner is outside"):
        _finding(effective_owner="auditor")
    with pytest.raises(ValueError, match="recommendation is outside"):
        _finding(recommendation="")
    with pytest.raises(ValueError, match="consequence is outside"):
        _finding(consequence="")
    with pytest.raises(ValueError, match="dedupe key is outside"):
        _finding(dedupe_key="!!")
    with pytest.raises(ValueError, match="timezone-aware"):
        _finding(deadline=datetime(2026, 8, 5))  # noqa: DTZ001


def test_finding_disposition_rejects_malformed_identities_and_reason() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        FindingDisposition(
            client_command_id=uuid4(),
            finding_id=cast(UUID, "not-a-uuid"),
            outcome=FindingDispositionOutcome.RESOLVED,
            reason="Decision made",
        )
    with pytest.raises(ValueError, match="reason is outside"):
        FindingDisposition(
            client_command_id=uuid4(),
            finding_id=uuid4(),
            outcome=FindingDispositionOutcome.RESOLVED,
            reason="",
        )


_SUBJECT_TICKET_ID = UUID(int=1)


def _finding(
    *,
    subject_ticket_id: UUID = _SUBJECT_TICKET_ID,
    kind_key: str = "needs_decision",
    reason_code: str = "gate_decision",
    effective_owner: str = "operator",
    recommendation: str = "Approve the release train",
    consequence: str = "Release stays blocked",
    deadline: datetime | None = None,
    dedupe_key: str = "release-gate-1",
) -> AppendFinding:
    return AppendFinding(
        client_command_id=uuid4(),
        subject_ticket_id=subject_ticket_id,
        kind_key=kind_key,
        reason_code=reason_code,
        effective_owner=effective_owner,
        recommendation=recommendation,
        alternatives=(),
        consequence=consequence,
        deadline=deadline,
        dedupe_key=dedupe_key,
        source_facts=(),
    )
