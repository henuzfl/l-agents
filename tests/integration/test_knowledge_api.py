from dataclasses import asdict

import httpx
import pytest

from app.api.dependencies import get_knowledge_document_service
from app.knowledge.uploads import DocumentJob, PipelineStage


class FakeKnowledgeDocumentService:
    max_upload_bytes = 1024
    processed: list[str] = []

    def start_upload(self, filename: str, content: bytes, _content_type: str) -> DocumentJob:
        assert content == "知识正文".encode()
        return DocumentJob(
            task_id="task-1",
            filename=filename,
            object_name="2026/08/26/task-1/manual.txt",
            status="processing",
            loading=PipelineStage("completed", "已保存到 knowledge-documents"),
            chunking=PipelineStage(),
            embedding=PipelineStage(),
            chunk_count=None,
            created_at="2026-08-26T00:00:00+00:00",
            updated_at="2026-08-26T00:00:00+00:00",
        )

    def process(self, task_id: str) -> None:
        self.processed.append(task_id)

    def get_job(self, _task_id: str) -> DocumentJob:
        return self.start_upload("manual.txt", "知识正文".encode(), "text/plain")

    def list_jobs(self) -> list[dict[str, object]]:
        return [asdict(self.get_job("task-1"))]

    def status(self) -> dict[str, int | str]:
        return {
            "schema": "agent_knowledge",
            "table": "project_manual",
            "node_count": 9,
            "embedding_model": "text-embedding-v4",
            "embedding_dimensions": 1024,
        }

    def download(self, _task_id: str) -> tuple[str, str, bytes]:
        return "manual.txt", "text/plain", b"knowledge"

    def list_chunks(self, task_id: str, **_filters: object) -> dict[str, object]:
        return {
            "task_id": task_id,
            "filename": "manual.txt",
            "minio_bucket": "knowledge-documents",
            "minio_object": "2026/08/26/task-1/manual.txt",
            "download_url": f"/api/v1/knowledge/documents/{task_id}/download",
            "total": 1,
            "offset": 0,
            "limit": 100,
            "chunks": [
                {
                    "position": 1,
                    "node_id": "node-1",
                    "content": "知识正文",
                    "element_type": "text",
                    "minio_object": "2026/08/26/task-1/manual.txt",
                }
            ],
        }

    def restart(self, task_id: str) -> DocumentJob:
        return self.get_job(task_id)

    def delete(self, _task_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_knowledge_page_contains_background_pipeline(client: httpx.AsyncClient) -> None:
    response = await client.get("/knowledge")
    assert response.status_code == 200
    assert "文档列表" in response.text
    assert 'id="openUploadButton"' in response.text
    assert 'role="dialog"' in response.text
    assert "Loading" in response.text
    assert "Chunking" in response.text
    assert "Embedding" in response.text
    assert "原文与分片" in response.text


@pytest.mark.asyncio
async def test_upload_returns_accepted_job_and_runs_background_task(
    client: httpx.AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    service = FakeKnowledgeDocumentService()
    app.dependency_overrides[get_knowledge_document_service] = lambda: service

    upload = await client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("manual.txt", "知识正文".encode(), "text/plain")},
    )

    assert upload.status_code == 202
    assert upload.json()["task_id"] == "task-1"
    assert upload.json()["loading"]["state"] == "completed"
    assert service.processed == ["task-1"]


@pytest.mark.asyncio
async def test_document_management_endpoints(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    service = FakeKnowledgeDocumentService()
    app.dependency_overrides[get_knowledge_document_service] = lambda: service

    listing = await client.get("/api/v1/knowledge/documents")
    chunks = await client.get("/api/v1/knowledge/documents/task-1/chunks")
    download = await client.get("/api/v1/knowledge/documents/task-1/download")
    reprocess = await client.post("/api/v1/knowledge/documents/task-1/reprocess")
    deletion = await client.delete("/api/v1/knowledge/documents/task-1")

    assert listing.status_code == 200
    assert listing.json()[0]["filename"] == "manual.txt"
    assert chunks.status_code == 200
    assert chunks.json()["chunks"][0]["node_id"] == "node-1"
    assert chunks.json()["chunks"][0]["minio_object"].endswith("manual.txt")
    assert download.content == b"knowledge"
    assert "manual.txt" in download.headers["content-disposition"]
    assert reprocess.status_code == 202
    assert deletion.status_code == 204
