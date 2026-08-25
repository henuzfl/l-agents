from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_knowledge_document_service
from app.knowledge import InvalidKnowledgeDocument, KnowledgeDocumentService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/status")
async def knowledge_status(
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> dict[str, int | str]:
    return await run_in_threadpool(service.status)


@router.post("/documents", status_code=201)
async def upload_knowledge_document(
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
    file: Annotated[UploadFile, File(description="知识库文档")],
) -> dict[str, int | str]:
    filename = file.filename or ""
    content = await file.read(service.max_upload_bytes + 1)
    await file.close()
    try:
        return await run_in_threadpool(service.upload, filename, content)
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
