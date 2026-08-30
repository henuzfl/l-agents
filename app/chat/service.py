from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agents import Agent, RunConfig
from agents.memory import Session

from app.chat.runner import AgentRunner, StreamingRunResult
from app.chat.stream_orchestrator import StreamOrchestrator
from app.chat.trace_mapper import SafeTraceMapper
from app.core.exceptions import AgentExecutionError, SessionError
from app.knowledge.retrieval.events import (
    EvidenceItem,
    bind_retrieval_evidence_sink,
    reset_retrieval_evidence_sink,
)
from app.knowledge.retrieval.service import KnowledgeSearchService
from app.memory import SessionFactory
from app.memory.short_term import ShortTermMemoryOptimizer
from app.schemas import ChatRequest, ChatResponse


class ChatService:
    def __init__(
        self,
        manager_agent: Agent[None],
        session_factory: SessionFactory,
        runner: AgentRunner,
        memory_optimizer: ShortTermMemoryOptimizer | None = None,
        stream_orchestrator: StreamOrchestrator | None = None,
    ) -> None:
        self._manager_agent = manager_agent
        self._session_factory = session_factory
        self._runner = runner
        self._memory_optimizer = memory_optimizer
        self._stream_orchestrator = stream_orchestrator or StreamOrchestrator()

    async def _run_config(self, session: Session, message: str) -> RunConfig | None:
        if self._memory_optimizer is None:
            return None
        return await self._memory_optimizer.prepare_run_config(session, message)

    async def chat(self, request: ChatRequest, user_id: str) -> ChatResponse:
        evidence_items: list[EvidenceItem] = []

        async def receive_evidence(items: list[EvidenceItem]) -> None:
            evidence_items.extend(items)

        evidence_token = bind_retrieval_evidence_sink(receive_evidence)
        try:
            session = self._session_factory.create(user_id, request.conversation_id)
            run_config = await self._run_config(session, request.message)
            if run_config is None:
                result = await self._runner.run(
                    self._manager_agent,
                    request.message,
                    session=session,
                )
            else:
                result = await self._runner.run(
                    self._manager_agent,
                    request.message,
                    session=session,
                    run_config=run_config,
                )
        except SessionError:
            raise
        except Exception as exc:
            raise AgentExecutionError("The manager agent could not complete the request.") from exc
        finally:
            reset_retrieval_evidence_sink(evidence_token)

        answer = str(result.final_output or "").strip()
        if not answer:
            raise AgentExecutionError("The manager agent returned an empty response.")
        return ChatResponse(
            conversation_id=request.conversation_id,
            answer=answer,
            evidence=KnowledgeSearchService.merge_evidence(evidence_items),
        )

    async def stream(self, request: ChatRequest, user_id: str) -> AsyncIterator[dict[str, Any]]:
        started_at = time.monotonic()
        mapper = SafeTraceMapper(started_at)
        yield {
            "type": "start",
            "conversation_id": request.conversation_id,
            "run_id": uuid4().hex,
            "started_at": datetime.now(UTC).isoformat(),
        }
        initial = mapper.trace(
            label="Manager 正在分析请求",
            status="running",
            agent="manager",
            dedupe_key="outer:agent:manager",
        )
        if initial is not None:
            yield initial

        result: StreamingRunResult | None = None
        try:
            session = self._session_factory.create(user_id, request.conversation_id)
            run_config = await self._run_config(session, request.message)
            if run_config is None:
                result = self._runner.run_streamed(
                    self._manager_agent,
                    request.message,
                    session=session,
                )
            else:
                result = self._runner.run_streamed(
                    self._manager_agent,
                    request.message,
                    session=session,
                    run_config=run_config,
                )
            async for event in self._stream_orchestrator.stream(result, mapper):
                yield event
        except asyncio.CancelledError:
            if result is not None:
                result.cancel()
            raise
        except Exception as exc:
            if result is not None:
                result.cancel()
            message = (
                str(exc)
                if isinstance(exc, SessionError | AgentExecutionError)
                else "The manager agent could not complete the request."
            )
            yield {
                "type": "error",
                "error_type": type(exc).__name__,
                "message": message,
                "duration_ms": mapper.elapsed_ms(),
            }
