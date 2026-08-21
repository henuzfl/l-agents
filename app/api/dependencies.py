from fastapi import Request

from app.container import Container
from app.services import ChatService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_chat_service(request: Request) -> ChatService:
    return get_container(request).chat_service
