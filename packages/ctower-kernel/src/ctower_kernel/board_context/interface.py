"""Small Interface for Board card context-set write commands (INV-66)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ctower_kernel.board_context.change_references import (
    ChangeReferenceCommand,
    ChangeReferenceResult,
)
from ctower_kernel.board_context.labels import ApplyLabelCommand, ApplyLabelResult
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["BoardContextFacts"]


class _BoardContextStore(Protocol):
    def record_change_reference(
        self,
        actor: Actor,
        command: ChangeReferenceCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ChangeReferenceResult | RecordProblem: ...

    def apply_label(
        self,
        actor: Actor,
        command: ApplyLabelCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ApplyLabelResult | RecordProblem: ...


class BoardContextFacts:
    """Append the Change-reference and applied-label facts the Board card reads."""

    def __init__(self, store: _BoardContextStore) -> None:
        self._store = store

    def record_change_reference(
        self,
        actor: Actor,
        command: ChangeReferenceCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ChangeReferenceResult | RecordProblem:
        return self._store.record_change_reference(
            actor, command, request_digest=request_digest, now=now, telemetry=telemetry
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
        return self._store.apply_label(
            actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )
