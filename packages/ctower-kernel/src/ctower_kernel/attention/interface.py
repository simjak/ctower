"""Small Attention Interface for authenticated poison recovery actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor

__all__ = [
    "Attention",
    "PoisonDisposition",
    "PoisonDispositionAction",
    "PoisonDispositionReceipt",
]

_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_MAX_REASON_LENGTH = 500


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


@dataclass(frozen=True, slots=True)
class PoisonDispositionReceipt:
    tenant_id: UUID
    actor_principal_id: UUID
    command: PoisonDisposition
    recorded_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command.client_command_id),
            "outbox_id": str(self.command.outbox_id),
            "action": self.command.action.value,
            "recorded_at": self.recorded_at.isoformat(),
        }


class _AttentionStore(Protocol):
    def disposition(self, actor: Actor, command: PoisonDisposition) -> PoisonDispositionReceipt: ...


class Attention:
    """Append authenticated actions without mutating poison or findings."""

    def __init__(self, store: _AttentionStore) -> None:
        self._store = store

    def disposition(self, actor: Actor, command: PoisonDisposition) -> PoisonDispositionReceipt:
        return self._store.disposition(actor, command)
