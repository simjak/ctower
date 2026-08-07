"""Small knowledge-base authority Interface."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["Knowledge"]


class _KnowledgeStore(Protocol):
    def register(
        self,
        actor: Actor,
        command: KnowledgeAddCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> KnowledgeAddResult | RecordProblem: ...

    def list_by_scope(self, actor: Actor, scope: str) -> KnowledgeDocumentListResult: ...

    def get(self, actor: Actor, document_id: UUID) -> KnowledgeDocument | None: ...


class Knowledge:
    """Register knowledge documents and read them back from the documents projection."""

    def __init__(self, store: _KnowledgeStore) -> None:
        self._store = store

    def register(
        self,
        actor: Actor,
        command: KnowledgeAddCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> KnowledgeAddResult | RecordProblem:
        return self._store.register(
            actor, command, request_digest=request_digest, now=now, telemetry=telemetry
        )

    def list_by_scope(self, actor: Actor, scope: str) -> KnowledgeDocumentListResult:
        return self._store.list_by_scope(actor, scope)

    def get(self, actor: Actor, document_id: UUID) -> KnowledgeDocument | None:
        return self._store.get(actor, document_id)
