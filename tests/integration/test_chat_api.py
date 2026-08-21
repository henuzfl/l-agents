import httpx
import pytest

from app.api.dependencies import get_chat_service
from app.core.exceptions import AgentExecutionError
from app.schemas import ChatRequest, ChatResponse


class FakeChatService:
    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            conversation_id=request.conversation_id,
            answer="这是 agent1 的固定返回结果。",
        )


class FailingChatService:
    async def chat(self, _request: ChatRequest) -> ChatResponse:
        raise AgentExecutionError("safe error")


@pytest.mark.asyncio
async def test_chat_supports_fake_service_injection(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    response = await client.post(
        "/api/v1/chat",
        json={
            "user_id": "user-001",
            "conversation_id": "conversation-001",
            "message": "请调用agent1",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-001",
        "answer": "这是 agent1 的固定返回结果。",
    }


@pytest.mark.asyncio
async def test_chat_rejects_empty_fields(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"user_id": "", "conversation_id": "conversation-001", "message": " "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_translates_application_errors(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: FailingChatService()
    response = await client.post(
        "/api/v1/chat",
        json={"user_id": "u", "conversation_id": "c", "message": "hello"},
    )
    assert response.status_code == 503
    assert response.json() == {
        "error": {"type": "AgentExecutionError", "message": "safe error"}
    }
