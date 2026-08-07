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
from ctower_kernel.knowledge.source import KnowledgeSource
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["PostgresKnowledge"]


class PostgresKnowledge:
    def __init__(self, dsn: str, *, source: KnowledgeSource | None = None) -> None:
        self._dsn = dsn
        self._source = source

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
                source=self._source,
            )
        )

    def list_by_scope(
        self, actor: Actor, scope: str, project_key: str | None = None
    ) -> KnowledgeDocumentListResult | RecordProblem:
        return list_documents(self._dsn, actor, scope, project_key)

    def get(
        self,
        actor: Actor,
        document_id: UUID,
        *,
        scope: str,
        project_key: str | None = None,
    ) -> KnowledgeDocument | RecordProblem:
        return get_document(self._dsn, actor, document_id, scope=scope, project_key=project_key)
