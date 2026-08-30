from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthenticatedUser, AuthService
from app.auth.dependencies import authenticate_bearer
from app.bootstrap import Container
from app.chat import ChatService
from app.knowledge import KnowledgeDocumentService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_chat_service(request: Request) -> ChatService:
    return get_container(request).chat_service


def get_auth_service(request: Request) -> AuthService:
    return get_container(request).auth_service


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthenticatedUser:
    return await authenticate_bearer(credentials, service)


def get_knowledge_document_service(request: Request) -> KnowledgeDocumentService:
    return get_container(request).knowledge_document_service
