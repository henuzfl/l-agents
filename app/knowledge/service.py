"""Compatibility exports for the knowledge retrieval package."""

from app.knowledge.retrieval.service import (
    NO_EVIDENCE_MESSAGE,
    KnowledgeSearchService,
    RetrieverLike,
)

__all__ = ["KnowledgeSearchService", "NO_EVIDENCE_MESSAGE", "RetrieverLike"]
