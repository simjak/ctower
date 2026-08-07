"""Knowledge base aggregate: registered documents with org/project scope."""

from ctower_kernel.knowledge.interface import Knowledge
from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)
from ctower_kernel.knowledge.postgres import PostgresKnowledge
from ctower_kernel.knowledge.source import (
    KnowledgeSource,
    KnowledgeSourceDocument,
    KnowledgeSourceUnavailableError,
    StaticFileKnowledgeSource,
    bundled_static_root,
)

__all__ = [
    "Knowledge",
    "KnowledgeAddCommand",
    "KnowledgeAddResult",
    "KnowledgeDocument",
    "KnowledgeDocumentListResult",
    "KnowledgeSource",
    "KnowledgeSourceDocument",
    "KnowledgeSourceUnavailableError",
    "PostgresKnowledge",
    "StaticFileKnowledgeSource",
    "bundled_static_root",
]
