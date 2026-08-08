"""PostgreSQL native-inbox authority implementation."""

from __future__ import annotations

from datetime import datetime

from ctower_kernel.inbox._delivery_sql import acknowledge_message
from ctower_kernel.inbox._promotion_sql import promote_thread
from ctower_kernel.inbox._sql import send_message
from ctower_kernel.inbox.models import (
    InboxAcknowledgeCommand,
    InboxAcknowledgeResult,
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresInbox"]


class PostgresInbox:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def acknowledge(
        self,
        actor: Actor,
        command: InboxAcknowledgeCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxAcknowledgeResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: acknowledge_message(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def send(
        self,
        actor: Actor,
        command: InboxSendCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxSendResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: send_message(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
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
        return recover_ambiguous_commit(
            lambda: promote_thread(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )
