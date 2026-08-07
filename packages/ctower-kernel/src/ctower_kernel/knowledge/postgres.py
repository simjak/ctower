"""PostgreSQL knowledge-base authority implementation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.knowledge._sql import get_document, list_documents, register_document
from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresKnowledge"]


class PostgresKnowledge:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def register(
        self,
        actor: Actor,
        command: KnowledgeAddCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> KnowledgeAddResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: register_document(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def list_by_scope(self, actor: Actor, scope: str) -> KnowledgeDocumentListResult:
        return list_documents(self._dsn, actor, scope)

    def get(self, actor: Actor, document_id: UUID) -> KnowledgeDocument | None:
        return get_document(self._dsn, actor, document_id)
