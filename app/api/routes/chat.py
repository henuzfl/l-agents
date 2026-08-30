import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service, get_current_user
from app.auth import AuthenticatedUser
from app.chat import ChatService
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


def encode_sse(payload: dict[str, Any]) -> str:
    if payload["type"] == "heartbeat":
        return ": heartbeat\n\n"
    event_name = str(payload["type"])
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\ndata: {data}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ChatResponse:
    return await service.chat(request, str(user.id))


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for payload in service.stream(request, str(user.id)):
            yield encode_sse(payload)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
