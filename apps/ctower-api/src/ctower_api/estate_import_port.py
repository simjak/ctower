"""Public application port for operator-authority estate imports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ctower_api.estate_import_contracts import EstateImportBatchResult
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["EstateImportPort"]


class EstateImportPort(Protocol):
    """Small application-to-importer port for one operator estate batch."""

    def import_batch(
        self,
        actor: Actor,
        *,
        tier: str,
        batch_index: int,
        command_id: UUID,
        manifest: Mapping[str, object],
        rows: Sequence[Mapping[str, object]],
        now: datetime,
        telemetry: TelemetryContext,
    ) -> EstateImportBatchResult | Mapping[str, object] | RecordProblem: ...
