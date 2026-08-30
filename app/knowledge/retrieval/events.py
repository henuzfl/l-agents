from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

EvidenceItem = dict[str, Any]
EvidenceSink = Callable[[list[EvidenceItem]], Awaitable[None]]

_evidence_sink: ContextVar[EvidenceSink | None] = ContextVar(
    "knowledge_evidence_sink",
    default=None,
)


async def publish_retrieval_evidence(items: list[EvidenceItem]) -> None:
    sink = _evidence_sink.get()
    if sink is not None and items:
        await sink(items)


def bind_retrieval_evidence_sink(sink: EvidenceSink) -> Any:
    return _evidence_sink.set(sink)


def reset_retrieval_evidence_sink(token: Any) -> None:
    _evidence_sink.reset(token)


__all__ = [
    "EvidenceItem",
    "bind_retrieval_evidence_sink",
    "publish_retrieval_evidence",
    "reset_retrieval_evidence_sink",
]
