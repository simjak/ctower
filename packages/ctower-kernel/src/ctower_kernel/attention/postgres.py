"""PostgreSQL implementation behind the Attention Interface."""

from __future__ import annotations

from ctower_kernel.attention import PoisonDisposition, PoisonDispositionReceipt
from ctower_kernel.attention._postgres_sql import disposition as _disposition
from ctower_kernel.record import Actor

__all__ = ["PostgresAttention"]


class PostgresAttention:
    """Persist append-only poison recovery commands under service authority."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def disposition(self, actor: Actor, command: PoisonDisposition) -> PoisonDispositionReceipt:
        return _disposition(self._dsn, actor, command)
