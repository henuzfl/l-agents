import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service
from app.schemas import ChatRequest, ChatResponse
from app.services import ChatService

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
) -> ChatResponse:
    return await service.chat(request)


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for payload in service.stream(request):
            yield encode_sse(payload)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
