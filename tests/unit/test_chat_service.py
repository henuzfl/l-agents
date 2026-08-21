from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from agents import Agent
from agents.memory import Session

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
        assert input == "请调用agent1"
        self.session = session
        return FakeResult("这是 agent1 的固定返回结果。")


@pytest.mark.asyncio
async def test_chat_service_passes_session_only_to_manager_run(tmp_path: Path) -> None:
    runner = FakeRunner()
    manager = Agent(name="manager", model="test-model")
    service = ChatService(
        manager,
        SessionFactory(tmp_path / "sessions.db"),
        runner,
    )
    response = await service.chat(
        ChatRequest(
            user_id="user-001",
            conversation_id="conversation-001",
            message="请调用agent1",
        )
    )
    assert runner.session is not None
    assert runner.session.session_id == "user-001:conversation-001"
    assert response.answer == "这是 agent1 的固定返回结果。"
