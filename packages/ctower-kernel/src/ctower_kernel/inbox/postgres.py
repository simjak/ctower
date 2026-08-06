"""PostgreSQL native-inbox authority implementation."""

from __future__ import annotations

from datetime import datetime

from ctower_kernel.inbox._sql import promote_thread, send_message
from ctower_kernel.inbox.models import (
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresInbox"]


class PostgresInbox:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def send(
        self,
        actor: Actor,
        command: InboxSendCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> InboxSendResult | RecordProblem:
        return send_message(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
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
        return promote_thread(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
