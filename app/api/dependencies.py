from fastapi import Request

from app.container import Container
from app.knowledge import KnowledgeDocumentService
from app.services import ChatService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_chat_service(request: Request) -> ChatService:
    return get_container(request).chat_service


def get_knowledge_document_service(request: Request) -> KnowledgeDocumentService:
    return get_container(request).knowledge_document_service
