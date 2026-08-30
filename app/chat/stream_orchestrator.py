import asyncio
from collections.abc import AsyncIterator
from typing import Any

from agents import AgentUpdatedStreamEvent

from app.chat.execution_events import bind_nested_event_sink, reset_nested_event_sink
from app.chat.runner import StreamingRunResult
from app.chat.trace_mapper import SafeTraceMapper, chunk_answer
from app.core.exceptions import AgentExecutionError
from app.knowledge.retrieval.events import (
    EvidenceItem,
    bind_retrieval_evidence_sink,
    reset_retrieval_evidence_sink,
)
from app.knowledge.retrieval.service import KnowledgeSearchService


class StreamOrchestrator:
    async def stream(
        self,
        result: StreamingRunResult,
        mapper: SafeTraceMapper,
    ) -> AsyncIterator[dict[str, Any]]:
        nested_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        evidence_items: list[EvidenceItem] = []

        async def receive_nested(payload: dict[str, Any]) -> None:
            await nested_queue.put(payload)

        async def receive_evidence(items: list[EvidenceItem]) -> None:
            evidence_items.extend(items)

        nested_token = bind_nested_event_sink(receive_nested)
        evidence_token = bind_retrieval_evidence_sink(receive_evidence)
        pending: set[asyncio.Task[Any]] = set()
        try:
            outer_events = result.stream_events().__aiter__()
            outer_task: asyncio.Task[Any] | None = asyncio.create_task(anext(outer_events))
            nested_task: asyncio.Task[Any] = asyncio.create_task(nested_queue.get())
            heartbeat_task: asyncio.Task[Any] = asyncio.create_task(asyncio.sleep(15))

            while outer_task is not None:
                pending = {outer_task, nested_task, heartbeat_task}
                completed, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                if nested_task in completed:
                    payload = nested_task.result()
                    nested_agent = payload["agent"].name
                    trace = mapper.map(
                        payload["event"],
                        scope=f"nested:{nested_agent}",
                        agent_name=nested_agent,
                    )
                    if trace is not None:
                        yield trace
                    nested_task = asyncio.create_task(nested_queue.get())
                if heartbeat_task in completed:
                    yield {"type": "heartbeat"}
                    heartbeat_task = asyncio.create_task(asyncio.sleep(15))
                if outer_task in completed:
                    try:
                        event = outer_task.result()
                    except StopAsyncIteration:
                        outer_task = None
                    else:
                        if isinstance(event, AgentUpdatedStreamEvent):
                            result.current_agent = event.new_agent
                        trace = mapper.map(
                            event,
                            scope="outer",
                            agent_name=result.current_agent.name,
                        )
                        if trace is not None:
                            yield trace
                        outer_task = asyncio.create_task(anext(outer_events))

            while not nested_queue.empty():
                payload = nested_queue.get_nowait()
                nested_agent = payload["agent"].name
                trace = mapper.map(
                    payload["event"],
                    scope=f"nested:{nested_agent}",
                    agent_name=nested_agent,
                )
                if trace is not None:
                    yield trace

            answer = str(result.final_output or "").strip()
            if not answer:
                raise AgentExecutionError("The manager agent returned an empty response.")
            completed = mapper.trace(
                label="Manager 已完成回答",
                status="completed",
                agent="manager",
                dedupe_key="outer:completed",
            )
            if completed is not None:
                yield completed
            for chunk in chunk_answer(answer):
                yield {"type": "delta", "text": chunk}
                await asyncio.sleep(0)
            yield {
                "type": "done",
                "answer": answer,
                "evidence": KnowledgeSearchService.merge_evidence(evidence_items),
                "duration_ms": mapper.elapsed_ms(),
                "step_count": mapper.sequence,
            }
        finally:
            reset_retrieval_evidence_sink(evidence_token)
            reset_nested_event_sink(nested_token)
            for task in pending:
                if not task.done():
                    task.cancel()
