import httpx
import pytest

from app.api.dependencies import get_chat_service, get_current_user
from app.core.exceptions import AgentExecutionError
from app.schemas import ChatRequest, ChatResponse


class FakeChatService:
    async def chat(self, request: ChatRequest, _user_id: str) -> ChatResponse:
        return ChatResponse(
            conversation_id=request.conversation_id,
            answer="这是知识检索 Agent 的返回结果。",
        )

    async def stream(self, request: ChatRequest, _user_id: str):  # type: ignore[no-untyped-def]
        yield {
            "type": "start",
            "conversation_id": request.conversation_id,
            "run_id": "run-1",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        yield {
            "type": "trace",
            "sequence": 1,
            "status": "running",
            "label": "Manager 正在分析请求",
            "agent": "manager",
            "tool": None,
            "elapsed_ms": 0,
        }
        yield {"type": "delta", "text": "流式回答"}
        yield {"type": "done", "answer": "流式回答", "duration_ms": 10, "step_count": 1}


class FailingChatService:
    async def chat(self, _request: ChatRequest, _user_id: str) -> ChatResponse:
        raise AgentExecutionError("safe error")


@pytest.mark.asyncio
async def test_chat_requires_authentication(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides.pop(get_current_user, None)
    response = await client.post(
        "/api/v1/chat",
        json={"conversation_id": "c", "message": "hello"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_supports_fake_service_injection(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "conversation-001",
            "message": "请调用知识检索 Agent",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-001",
        "answer": "这是知识检索 Agent 的返回结果。",
        "evidence": [],
    }


@pytest.mark.asyncio
async def test_chat_rejects_empty_fields(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"conversation_id": "conversation-001", "message": " "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_translates_application_errors(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: FailingChatService()
    response = await client.post(
        "/api/v1/chat",
        json={"conversation_id": "c", "message": "hello"},
    )
    assert response.status_code == 503
    assert response.json() == {
        "error": {"type": "AgentExecutionError", "message": "safe error"}
    }


@pytest.mark.asyncio
async def test_chat_stream_returns_ordered_sse_events(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    response = await client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "stream-c", "message": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.index("event: start") < response.text.index("event: trace")
    assert response.text.index("event: trace") < response.text.index("event: delta")
    assert response.text.index("event: delta") < response.text.index("event: done")
    assert "raw_item" not in response.text
