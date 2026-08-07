"""Small native-inbox authority Interface."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ctower_kernel.inbox.models import (
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["Inbox"]


class _InboxStore(Protocol):
    def send(
        self,
        actor: Actor,
        command: InboxSendCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxSendResult | RecordProblem: ...

    def promote(
        self,
        actor: Actor,
        command: InboxPromotionCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxPromotionResult | RecordProblem: ...


class Inbox:
    """Append messages and durable thread-to-ticket promotion facts."""

    def __init__(self, store: _InboxStore) -> None:
        self._store = store

    def send(
        self,
        actor: Actor,
        command: InboxSendCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxSendResult | RecordProblem:
        return self._store.send(
            actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )

    def promote(
        self,
        actor: Actor,
        command: InboxPromotionCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxPromotionResult | RecordProblem:
        return self._store.promote(
            actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )
