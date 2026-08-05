"""PostgreSQL implementation behind the Attention Interface."""

from __future__ import annotations

from ctower_kernel.attention import (
    AppendFinding,
    AttentionFindingReceipt,
    FindingDisposition,
    FindingDispositionReceipt,
    PoisonDisposition,
    PoisonDispositionReceipt,
)
from ctower_kernel.attention._findings_sql import append_finding as _append_finding
from ctower_kernel.attention._findings_sql import (
    record_finding_disposition as _record_finding_disposition,
)
from ctower_kernel.attention._postgres_sql import disposition as _disposition
from ctower_kernel.record import Actor, RecordProblem

__all__ = ["PostgresAttention"]


class PostgresAttention:
    """Persist append-only poison recovery commands and Attention findings."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def disposition(
        self, actor: Actor, command: PoisonDisposition
    ) -> PoisonDispositionReceipt | RecordProblem:
        return _disposition(self._dsn, actor, command)

    def append_finding(
        self, actor: Actor, command: AppendFinding
    ) -> AttentionFindingReceipt | RecordProblem:
        return _append_finding(self._dsn, actor, command)

    def record_finding_disposition(
        self, actor: Actor, command: FindingDisposition
    ) -> FindingDispositionReceipt | RecordProblem:
        return _record_finding_disposition(self._dsn, actor, command)
