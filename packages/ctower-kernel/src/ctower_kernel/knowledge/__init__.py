"""Knowledge base aggregate: registered documents with org/project scope."""

from ctower_kernel.knowledge.interface import Knowledge
from ctower_kernel.knowledge.models import (
    KnowledgeAddCommand,
    KnowledgeAddResult,
    KnowledgeDocument,
    KnowledgeDocumentListResult,
)
from ctower_kernel.knowledge.postgres import PostgresKnowledge

__all__ = [
    "Knowledge",
    "KnowledgeAddCommand",
    "KnowledgeAddResult",
    "KnowledgeDocument",
    "KnowledgeDocumentListResult",
    "PostgresKnowledge",
]
