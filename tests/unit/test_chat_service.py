from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from agents import Agent, RawResponsesStreamEvent
from agents.memory import Session
from openai.types.responses import ResponseTextDeltaEvent
from sqlalchemy.ext.asyncio import create_async_engine

from app.knowledge.retrieval.events import publish_retrieval_evidence
from app.memory import SessionFactory
from app.schemas import ChatRequest
from app.services import ChatService


@dataclass
class FakeResult:
    final_output: str


class FakeRunner:
    def __init__(self) -> None:
        self.session: Session | None = None

    async def run(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
        **_kwargs: Any,
    ) -> FakeResult:
        assert starting_agent.name == "manager"
        assert input == "请调用知识检索 Agent"
        self.session = session
        await publish_retrieval_evidence(
            [
                {
                    "node_id": "node-1",
                    "source": "manual.pdf",
                    "section": "上传文档",
                    "page_number": 1,
                    "element_type": "image",
                    "content": "流程图",
                    "asset_url": "/api/v1/knowledge/documents/task-1/chunks/node-1/asset",
                }
            ]
        )
        return FakeResult("这是知识检索 Agent 的返回结果。")


class FakeStreamingResult:
    def __init__(self, agent: Agent[None]) -> None:
        self.current_agent = agent
        self.final_output = "流式回答"
        self.cancelled = False

    async def stream_events(self):  # type: ignore[no-untyped-def]
        await publish_retrieval_evidence(
            [
                {
                    "node_id": "node-stream",
                    "source": "manual.pdf",
                    "section": "上传文档",
                    "page_number": 2,
                    "element_type": "image",
                    "content": "流式图片",
                    "asset_url": "/api/v1/knowledge/documents/task-1/chunks/node-stream/asset",
                }
            ]
        )
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="PRIVATE-CHAIN-OF-THOUGHT",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            )
        )
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="PRIVATE-DRAFT",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=2,
                type="response.output_text.delta",
            )
        )

    def cancel(self, mode: str = "immediate") -> None:
        self.cancelled = True


class FakeStreamingRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.streaming_result: FakeStreamingResult | None = None

    def run_streamed(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
    ) -> FakeStreamingResult:
        assert input == "请流式回答"
        self.session = session
        self.streaming_result = FakeStreamingResult(starting_agent)
        return self.streaming_result


@pytest.mark.asyncio
async def test_chat_service_passes_session_only_to_manager_run(tmp_path: Path) -> None:
    runner = FakeRunner()
    manager = Agent(name="manager", model="test-model")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    service = ChatService(
        manager,
        SessionFactory(engine),
        runner,
    )
    response = await service.chat(
        ChatRequest(
            conversation_id="conversation-001",
            message="请调用知识检索 Agent",
        ),
        "user-001",
    )
    assert runner.session is not None
    assert runner.session.session_id == "user-001:conversation-001"
    assert response.answer == "这是知识检索 Agent 的返回结果。"
    assert [item.node_id for item in response.evidence] == ["node-1"]


@pytest.mark.asyncio
async def test_chat_service_streams_deltas_and_final_answer(tmp_path: Path) -> None:
    runner = FakeStreamingRunner()
    manager = Agent(name="manager", model="test-model")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    service = ChatService(manager, SessionFactory(engine), runner)

    events = [
        event
        async for event in service.stream(
            ChatRequest(
                conversation_id="conversation-stream",
                message="请流式回答",
            ),
            "user-001",
        )
    ]

    assert runner.session is not None
    assert runner.session.session_id == "user-001:conversation-stream"
    deltas = "".join(event["text"] for event in events if event["type"] == "delta")
    assert deltas == "流式回答"
    assert "PRIVATE" not in str(events)
    assert events[-1]["type"] == "done"
    assert events[-1]["answer"] == "流式回答"
    assert [item["node_id"] for item in events[-1]["evidence"]] == ["node-stream"]
