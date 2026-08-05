"""Small Attention Interface for authenticated poison recovery actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor, RecordProblem

__all__ = [
    "AppendFinding",
    "Attention",
    "AttentionFindingReceipt",
    "FindingDisposition",
    "FindingDispositionOutcome",
    "FindingDispositionReceipt",
    "PoisonDisposition",
    "PoisonDispositionAction",
    "PoisonDispositionReceipt",
]

_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_REASON_CODE = re.compile(r"^[a-z][a-z0-9._-]*$")
_DEDUPE_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
_MAX_REASON_LENGTH = 500
_MAX_TEXT_LENGTH = 500


class PoisonDispositionAction(StrEnum):
    RETRY = "retry"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True, slots=True)
class PoisonDisposition:
    client_command_id: UUID
    consumer_key: str
    topic: str
    outbox_id: UUID
    action: PoisonDispositionAction
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.outbox_id, UUID):
            raise TypeError("poison disposition identities must be UUIDs")
        if _KEY.fullmatch(self.consumer_key) is None or _KEY.fullmatch(self.topic) is None:
            raise ValueError("poison disposition partition keys are invalid")
        if not 1 <= len(self.reason) <= _MAX_REASON_LENGTH:
            raise ValueError("poison disposition reason is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "consumer_key": self.consumer_key,
            "outbox_id": str(self.outbox_id),
            "reason": self.reason,
            "topic": self.topic,
        }


@dataclass(frozen=True, slots=True)
class PoisonDispositionReceipt:
    tenant_id: UUID
    actor_principal_id: UUID
    command: PoisonDisposition
    recorded_at: datetime
    event_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command.client_command_id),
            "outbox_id": str(self.command.outbox_id),
            "action": self.command.action.value,
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "recorded_at": self.recorded_at.isoformat(),
        }


class FindingDispositionOutcome(StrEnum):
    """AC-ATT-02: resolution is data, never a row's disappearance."""

    RESOLVED = "resolved"
    SNOOZED = "snoozed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AppendFinding:
    """INV-67: one typed appended statement that work needs a human."""

    client_command_id: UUID
    subject_ticket_id: UUID
    kind_key: str
    reason_code: str
    effective_owner: str
    recommendation: str
    alternatives: tuple[str, ...]
    consequence: str
    deadline: datetime | None
    dedupe_key: str
    source_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate_identity()
        self._validate_content()

    def _validate_identity(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(
            self.subject_ticket_id, UUID
        ):
            raise TypeError("attention finding command identities must be UUIDs")
        if _KEY.fullmatch(self.kind_key) is None:
            raise ValueError("attention finding kind is outside the authored contract")
        if _REASON_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("attention finding reason code is outside the authored contract")
        if self.effective_owner not in {"operator", "commander"}:
            raise ValueError("attention finding owner is outside the authored contract")

    def _validate_content(self) -> None:
        if not 1 <= len(self.recommendation) <= _MAX_TEXT_LENGTH:
            raise ValueError("attention finding recommendation is outside the authored contract")
        if not 1 <= len(self.consequence) <= _MAX_TEXT_LENGTH:
            raise ValueError("attention finding consequence is outside the authored contract")
        if _DEDUPE_KEY.fullmatch(self.dedupe_key) is None:
            raise ValueError("attention finding dedupe key is outside the authored contract")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("attention finding deadline must be timezone-aware")

    def request_payload(self) -> dict[str, object]:
        return {
            "alternatives": list(self.alternatives),
            "consequence": self.consequence,
            "deadline": self.deadline.isoformat() if self.deadline is not None else None,
            "dedupe_key": self.dedupe_key,
            "effective_owner": self.effective_owner,
            "kind_key": self.kind_key,
            "reason_code": self.reason_code,
            "recommendation": self.recommendation,
            "source_facts": list(self.source_facts),
            "subject_ticket_id": str(self.subject_ticket_id),
        }


@dataclass(frozen=True, slots=True)
class AttentionFindingReceipt:
    tenant_id: UUID
    actor_principal_id: UUID
    command: AppendFinding
    finding_id: UUID
    recorded_at: datetime
    event_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command.client_command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "finding_id": str(self.finding_id),
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class FindingDisposition:
    client_command_id: UUID
    finding_id: UUID
    outcome: FindingDispositionOutcome
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.finding_id, UUID):
            raise TypeError("finding disposition command identities must be UUIDs")
        if not 1 <= len(self.reason) <= _MAX_REASON_LENGTH:
            raise ValueError("finding disposition reason is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "finding_id": str(self.finding_id),
            "outcome": self.outcome.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FindingDispositionReceipt:
    tenant_id: UUID
    actor_principal_id: UUID
    command: FindingDisposition
    recorded_at: datetime
    event_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command.client_command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "finding_id": str(self.command.finding_id),
            "outcome": self.command.outcome.value,
            "recorded_at": self.recorded_at.isoformat(),
        }


class _AttentionStore(Protocol):
    def disposition(
        self, actor: Actor, command: PoisonDisposition
    ) -> PoisonDispositionReceipt | RecordProblem: ...

    def append_finding(
        self, actor: Actor, command: AppendFinding
    ) -> AttentionFindingReceipt | RecordProblem: ...

    def record_finding_disposition(
        self, actor: Actor, command: FindingDisposition
    ) -> FindingDispositionReceipt | RecordProblem: ...


class Attention:
    """Append authenticated actions without mutating poison or findings."""

    def __init__(self, store: _AttentionStore) -> None:
        self._store = store

    def disposition(
        self, actor: Actor, command: PoisonDisposition
    ) -> PoisonDispositionReceipt | RecordProblem:
        return self._store.disposition(actor, command)

    def append_finding(
        self, actor: Actor, command: AppendFinding
    ) -> AttentionFindingReceipt | RecordProblem:
        return self._store.append_finding(actor, command)

    def record_finding_disposition(
        self, actor: Actor, command: FindingDisposition
    ) -> FindingDispositionReceipt | RecordProblem:
        return self._store.record_finding_disposition(actor, command)
