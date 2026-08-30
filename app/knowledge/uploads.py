from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from llama_index.core import Document
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.repositories import KnowledgeDocumentRepository

from .documents import build_document_nodes
from .domain import DocumentJob, PipelineStage
from .ingestion import (
    SUPPORTED_EXTENSIONS,
    InvalidKnowledgeDocument,
    extract_document_text,
    process_pdf,
)
from .storage import KnowledgeStatus, LlamaIndexKnowledgeStore, MinioDocumentStorage

StoreFactory = Callable[[Settings], LlamaIndexKnowledgeStore]


class DocumentRepository(Protocol):
    async def save(self, payload: dict[str, Any]) -> None: ...

    async def get(self, task_id: str) -> dict[str, Any] | None: ...

    async def list(self, limit: int = 100) -> list[dict[str, Any]]: ...

    async def delete(self, task_id: str) -> None: ...


class KnowledgeDocumentService:
    def __init__(
        self,
        settings: Settings,
        store_factory: StoreFactory = LlamaIndexKnowledgeStore,
        object_storage: MinioDocumentStorage | None = None,
        registry: DocumentRepository | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._settings = settings
        self._store_factory = store_factory
        self._object_storage = object_storage
        if registry is None and session_maker is None:
            raise ValueError("session_maker is required when registry is not provided")
        self._registry = registry or KnowledgeDocumentRepository(session_maker)  # type: ignore[arg-type]
        self._jobs: dict[str, DocumentJob] = {}
        self._lock = asyncio.Lock()

    async def recover_interrupted_jobs(self) -> None:
        await self._recover_interrupted_jobs()

    @property
    def max_upload_bytes(self) -> int:
        return self._settings.knowledge_upload_max_bytes

    def _storage(self) -> MinioDocumentStorage:
        if self._object_storage is None:
            self._object_storage = MinioDocumentStorage(self._settings)
        return self._object_storage

    async def _recover_interrupted_jobs(self) -> None:
        for payload in await self._registry.list():
            job = DocumentJob.from_dict(payload)
            if job.status != "processing":
                continue
            job.status = "failed"
            job.error = "服务重启导致后台处理被中断，请重新处理。"
            if job.chunking.state == "running":
                job.chunking = PipelineStage("failed", "后台处理已中断")
            elif job.embedding.state == "running":
                job.embedding = PipelineStage("failed", "后台处理已中断")
            job.updated_at = self._now()
            await self._registry.save(job.to_dict())

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    async def _update(self, task_id: str, **changes: object) -> None:
        async with self._lock:
            job = self._jobs[task_id]
            for name, value in changes.items():
                setattr(job, name, value)
            job.updated_at = self._now()
            await self._registry.save(job.to_dict())

    async def start_upload(
        self, filename: str, content: bytes, content_type: str | None
    ) -> DocumentJob:
        clean_filename = Path(filename).name
        if not clean_filename:
            raise InvalidKnowledgeDocument("文件名不能为空。")
        if Path(clean_filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            allowed = "、".join(sorted(SUPPORTED_EXTENSIONS))
            raise InvalidKnowledgeDocument(f"不支持该文件类型，可上传：{allowed}")
        if len(content) > self._settings.knowledge_upload_max_bytes:
            limit_mb = self._settings.knowledge_upload_max_bytes // (1024 * 1024)
            raise InvalidKnowledgeDocument(f"文件不能超过 {limit_mb} MB。")

        task_id = str(uuid4())
        date_path = datetime.now(UTC).strftime("%Y/%m/%d")
        object_name = f"{date_path}/{task_id}/{clean_filename}"
        now = self._now()
        job = DocumentJob(
            task_id=task_id,
            filename=clean_filename,
            object_name=object_name,
            status="processing",
            loading=PipelineStage("running", "正在上传原始文档到 MinIO"),
            chunking=PipelineStage(),
            embedding=PipelineStage(),
            chunk_count=None,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._jobs[task_id] = job
            await self._registry.save(job.to_dict())
        detected_type = content_type or mimetypes.guess_type(clean_filename)[0]
        try:
            await asyncio.to_thread(
                self._storage().upload,
                object_name,
                content,
                detected_type or "application/octet-stream",
            )
        except Exception as exc:
            await self._update(
                task_id,
                status="failed",
                loading=PipelineStage("failed", "原始文档上传失败"),
                error=str(exc),
            )
            raise
        await self._update(
            task_id,
            loading=PipelineStage("completed", f"已保存到 {self._storage().bucket}"),
            chunking=PipelineStage("pending", "后台任务等待开始"),
        )
        return await self.get_job(task_id)

    async def process(self, task_id: str) -> None:
        try:
            await self._update(
                task_id, chunking=PipelineStage("running", "正在提取并切分文本")
            )
            job = await self.get_job(task_id)
            content = await asyncio.to_thread(self._storage().download, job.object_name)
            if Path(job.filename).suffix.lower() == ".pdf":
                pdf_result = await asyncio.to_thread(
                    process_pdf,
                    content,
                    job.filename,
                    job.object_name,
                    self._settings,
                    self._storage().upload,
                )
                nodes = pdf_result.nodes
                warnings = pdf_result.warnings
                element_counts = pdf_result.element_counts
            else:
                text = await asyncio.to_thread(extract_document_text, job.filename, content)
                document = Document(
                    text=text,
                    metadata={
                        "source": job.filename,
                        "section": "上传文档",
                        "minio_bucket": self._storage().bucket,
                        "minio_object": job.object_name,
                    },
                )
                nodes = await asyncio.to_thread(build_document_nodes, document)
                warnings = []
                element_counts = {"text": len(nodes)}
            for node in nodes:
                node.metadata["task_id"] = task_id
            await self._update(
                task_id,
                chunk_count=len(nodes),
                warnings=warnings,
                element_counts=element_counts,
                chunking=PipelineStage("completed", f"已生成 {len(nodes)} 个文本块"),
                embedding=PipelineStage("running", "正在生成向量并写入索引"),
            )
            await asyncio.to_thread(self._store_factory(self._settings).add_nodes, nodes)
            await self._update(
                task_id,
                status="completed",
                embedding=PipelineStage("completed", "向量索引写入完成"),
            )
        except Exception as exc:
            async with self._lock:
                job = self._jobs[task_id]
                if job.chunking.state == "running":
                    job.chunking = PipelineStage("failed", "文档切分失败")
                elif job.embedding.state == "running":
                    job.embedding = PipelineStage("failed", "向量写入失败")
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = self._now()
                await self._registry.save(job.to_dict())

    async def get_job(self, task_id: str) -> DocumentJob:
        async with self._lock:
            job = self._jobs.get(task_id)
            if job is None:
                payload = await self._registry.get(task_id)
                if payload is None:
                    raise KeyError(task_id)
                job = DocumentJob.from_dict(payload)
                self._jobs[task_id] = job
            return deepcopy(job)

    async def list_jobs(self) -> list[dict[str, object]]:
        return await self._registry.list()

    async def download(self, task_id: str) -> tuple[str, str, bytes]:
        job = await self.get_job(task_id)
        content_type = mimetypes.guess_type(job.filename)[0] or "application/octet-stream"
        content = await asyncio.to_thread(self._storage().download, job.object_name)
        return job.filename, content_type, content

    async def download_asset(
        self, task_id: str, node_id: str
    ) -> tuple[str, str, bytes]:
        job = await self.get_job(task_id)
        if job.status != "completed":
            raise InvalidKnowledgeDocument("文档处理完成后才能查看图片。")
        chunk = await asyncio.to_thread(
            self._store_factory(self._settings).get_document_chunk,
            job.object_name,
            node_id,
        )
        asset_object = chunk.metadata.get("asset_object") if chunk is not None else None
        if not isinstance(asset_object, str) or not asset_object:
            raise KeyError(node_id)
        asset_prefix = f"{job.object_name.rsplit('/', 1)[0]}/assets/"
        if not asset_object.startswith(asset_prefix):
            raise InvalidKnowledgeDocument("分片图片不属于当前文档。")
        filename = Path(asset_object).name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        content = await asyncio.to_thread(self._storage().download, asset_object)
        return filename, content_type, content

    async def list_chunks(
        self,
        task_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        element_type: str | None = None,
        query: str | None = None,
    ) -> dict[str, object]:
        job = await self.get_job(task_id)
        if job.status != "completed":
            raise InvalidKnowledgeDocument("文档处理完成后才能查看分片。")
        total, chunks = await asyncio.to_thread(
            self._store_factory(self._settings).list_document_chunks,
            job.object_name,
            offset=offset,
            limit=limit,
            element_type=element_type,
            query=query,
        )
        return {
            "task_id": job.task_id,
            "filename": job.filename,
            "minio_bucket": self._storage().bucket,
            "minio_object": job.object_name,
            "download_url": f"/api/v1/knowledge/documents/{job.task_id}/download",
            "total": total,
            "offset": offset,
            "limit": limit,
            "chunks": [
                {
                    "position": offset + index,
                    "node_id": chunk.node_id,
                    "content": chunk.content,
                    "page_number": chunk.metadata.get("page_number"),
                    "section": chunk.metadata.get("section", "上传文档"),
                    "element_type": chunk.metadata.get("element_type", "text"),
                    "element_index": chunk.metadata.get("element_index"),
                    "element_part": chunk.metadata.get("element_part"),
                    "language": chunk.metadata.get("language"),
                    "minio_object": chunk.metadata.get("minio_object", job.object_name),
                    "asset_object": chunk.metadata.get("asset_object"),
                    "asset_url": (
                        f"/api/v1/knowledge/documents/{job.task_id}/chunks/"
                        f"{chunk.node_id}/asset"
                        if chunk.metadata.get("asset_object")
                        else None
                    ),
                }
                for index, chunk in enumerate(chunks, start=1)
            ],
        }

    async def restart(self, task_id: str) -> DocumentJob:
        job = await self.get_job(task_id)
        if job.status == "processing":
            raise InvalidKnowledgeDocument("文档正在处理中，不能重复执行。")
        await asyncio.to_thread(
            self._store_factory(self._settings).delete_document, job.object_name
        )
        await asyncio.to_thread(self._storage().delete_assets, job.object_name)
        await self._update(
            task_id,
            status="processing",
            chunk_count=None,
            warnings=[],
            element_counts={},
            chunking=PipelineStage("pending", "后台任务等待开始"),
            embedding=PipelineStage(),
            error=None,
        )
        return await self.get_job(task_id)

    async def delete(self, task_id: str) -> None:
        job = await self.get_job(task_id)
        if job.status == "processing":
            raise InvalidKnowledgeDocument("文档正在处理中，不能删除。")
        await asyncio.to_thread(
            self._store_factory(self._settings).delete_document, job.object_name
        )
        await asyncio.to_thread(self._storage().delete_assets, job.object_name)
        await asyncio.to_thread(self._storage().delete, job.object_name)
        async with self._lock:
            self._jobs.pop(task_id, None)
            await self._registry.delete(task_id)

    async def status(self) -> dict[str, int | str]:
        status: KnowledgeStatus = await asyncio.to_thread(
            self._store_factory(self._settings).status
        )
        return asdict(status)
