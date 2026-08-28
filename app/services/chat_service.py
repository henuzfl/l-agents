from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from agents import Agent, AgentUpdatedStreamEvent, RunConfig
from agents.memory import Session

from app.core.exceptions import AgentExecutionError, SessionError
from app.memory import SessionFactory
from app.memory.short_term import ShortTermMemoryOptimizer
from app.schemas import ChatRequest, ChatResponse

from .execution_events import bind_nested_event_sink, reset_nested_event_sink
from .stream_events import SafeTraceMapper, chunk_answer


class RunResultLike(Protocol):
    final_output: Any


class StreamingRunResultLike(Protocol):
    final_output: Any
    current_agent: Agent[Any]

    def stream_events(self) -> AsyncIterator[object]: ...

    def cancel(self, mode: str = "immediate") -> None: ...


class RunnerLike(Protocol):
    async def run(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
        run_config: RunConfig | None = None,
    ) -> RunResultLike: ...

    def run_streamed(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
        run_config: RunConfig | None = None,
    ) -> StreamingRunResultLike: ...


class ChatService:
    def __init__(
        self,
        manager_agent: Agent[None],
        session_factory: SessionFactory,
        runner: RunnerLike,
        memory_optimizer: ShortTermMemoryOptimizer | None = None,
    ) -> None:
        self._manager_agent = manager_agent
        self._session_factory = session_factory
        self._runner = runner
        self._memory_optimizer = memory_optimizer

    async def _run_config(self, session: Session, message: str) -> RunConfig | None:
        if self._memory_optimizer is None:
            return None
        return await self._memory_optimizer.prepare_run_config(session, message)

    async def chat(self, request: ChatRequest, user_id: str) -> ChatResponse:
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

        answer = str(result.final_output or "").strip()
        if not answer:
            raise AgentExecutionError("The manager agent returned an empty response.")
        return ChatResponse(conversation_id=request.conversation_id, answer=answer)

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

        nested_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def receive_nested(payload: dict[str, Any]) -> None:
            await nested_queue.put(payload)

        token = bind_nested_event_sink(receive_nested)
        result: StreamingRunResultLike | None = None
        pending: set[asyncio.Task[Any]] = set()
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
            outer_events = result.stream_events().__aiter__()
            outer_task: asyncio.Task[Any] | None = asyncio.create_task(anext(outer_events))
            nested_task: asyncio.Task[Any] = asyncio.create_task(nested_queue.get())
            heartbeat_task: asyncio.Task[Any] = asyncio.create_task(asyncio.sleep(15))

            while outer_task is not None:
                pending = {outer_task, nested_task, heartbeat_task}
                completed, _ = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if nested_task in completed:
                    payload = nested_task.result()
                    nested_event = payload["event"]
                    nested_agent = payload["agent"].name
                    trace = mapper.map(
                        nested_event,
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
            completed_trace = mapper.trace(
                label="Manager 已完成回答",
                status="completed",
                agent="manager",
                dedupe_key="outer:completed",
            )
            if completed_trace is not None:
                yield completed_trace
            for chunk in chunk_answer(answer):
                yield {"type": "delta", "text": chunk}
                await asyncio.sleep(0)
            yield {
                "type": "done",
                "answer": answer,
                "duration_ms": mapper.elapsed_ms(),
                "step_count": mapper.sequence,
            }
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
        finally:
            reset_nested_event_sink(token)
            for task in pending:
                if not task.done():
                    task.cancel()
