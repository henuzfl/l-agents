from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthenticatedUser, AuthenticationError, AuthService
from app.container import Container
from app.knowledge import KnowledgeDocumentService
from app.services import ChatService


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
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="需要登录。")
    try:
        return await service.current_user(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_knowledge_document_service(request: Request) -> KnowledgeDocumentService:
    return get_container(request).knowledge_document_service
