from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.api.dependencies import get_current_user, get_knowledge_document_service
from app.knowledge import InvalidKnowledgeDocument, KnowledgeDocumentService

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status")
async def knowledge_status(
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> dict[str, int | str]:
    return await service.status()


@router.get("/documents")
async def list_knowledge_documents(
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> list[dict[str, object]]:
    return await service.list_jobs()


@router.get("/documents/{task_id}")
async def get_knowledge_document_job(
    task_id: str,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> dict[str, object]:
    try:
        job = await service.get_job(task_id)
        return job.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="处理任务不存在。") from exc


@router.get("/documents/{task_id}/download")
async def download_knowledge_document(
    task_id: str,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> Response:
    try:
        filename, content_type, content = await service.download(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="文档不存在。") from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/documents/{task_id}/chunks")
async def list_knowledge_document_chunks(
    task_id: str,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    element_type: str | None = None,
    query: str | None = None,
) -> dict[str, object]:
    try:
        return await service.list_chunks(
            task_id,
            offset=offset,
            limit=limit,
            element_type=element_type,
            query=query,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="文档不存在。") from exc
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/documents/{task_id}/chunks/{node_id}/asset")
async def view_knowledge_chunk_asset(
    task_id: str,
    node_id: str,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> Response:
    try:
        filename, content_type, content = await service.download_asset(
            task_id,
            node_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="分片图片不存在。") from exc
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post("/documents/{task_id}/reprocess", status_code=202)
async def reprocess_knowledge_document(
    task_id: str,
    background_tasks: BackgroundTasks,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> dict[str, object]:
    try:
        job = await service.restart(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="文档不存在。") from exc
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(service.process, task_id)
    return job.to_dict()


@router.delete("/documents/{task_id}", status_code=204)
async def delete_knowledge_document(
    task_id: str,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
) -> Response:
    try:
        await service.delete(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="文档不存在。") from exc
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/documents", status_code=202)
async def upload_knowledge_document(
    background_tasks: BackgroundTasks,
    service: Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)],
    file: Annotated[UploadFile, File(description="知识库文档")],
) -> dict[str, object]:
    filename = file.filename or ""
    content = await file.read(service.max_upload_bytes + 1)
    await file.close()
    try:
        job = await service.start_upload(
            filename,
            content,
            file.content_type,
        )
        background_tasks.add_task(service.process, job.task_id)
        return job.to_dict()
    except InvalidKnowledgeDocument as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
