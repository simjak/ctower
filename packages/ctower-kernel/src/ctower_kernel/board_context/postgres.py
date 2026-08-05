"""PostgreSQL implementation behind the Board context-set facts Interface."""

from __future__ import annotations

from datetime import datetime

from ctower_kernel.board_context._change_reference_sql import (
    record_change_reference as _record_change_reference,
)
from ctower_kernel.board_context._label_sql import apply_label as _apply_label
from ctower_kernel.board_context.change_references import (
    ChangeReferenceCommand,
    ChangeReferenceResult,
)
from ctower_kernel.board_context.labels import ApplyLabelCommand, ApplyLabelResult
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresBoardContextFacts"]


class PostgresBoardContextFacts:
    """Persist append-only Change-reference and applied-label facts."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record_change_reference(
        self,
        actor: Actor,
        command: ChangeReferenceCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ChangeReferenceResult | RecordProblem:
        return _record_change_reference(
            self._dsn, actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )

    def apply_label(
        self,
        actor: Actor,
        command: ApplyLabelCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ApplyLabelResult | RecordProblem:
        return _apply_label(
            self._dsn, actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )
