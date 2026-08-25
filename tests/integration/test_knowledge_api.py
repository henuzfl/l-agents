import httpx
import pytest

from app.api.dependencies import get_knowledge_document_service


class FakeKnowledgeDocumentService:
    max_upload_bytes = 1024

    def upload(self, filename: str, content: bytes) -> dict[str, int | str]:
        assert content == "知识正文".encode()
        return {"filename": filename, "node_count": 2}

    def status(self) -> dict[str, int | str]:
        return {
            "schema": "agent_knowledge",
            "table": "project_manual",
            "node_count": 9,
            "embedding_model": "text-embedding-v4",
            "embedding_dimensions": 1024,
        }


@pytest.mark.asyncio
async def test_knowledge_page_contains_upload_interface(client: httpx.AsyncClient) -> None:
    response = await client.get("/knowledge")
    assert response.status_code == 200
    assert "添加文档" in response.text
    assert 'href="/knowledge"' in response.text


@pytest.mark.asyncio
async def test_upload_and_status_support_service_injection(client: httpx.AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_knowledge_document_service] = FakeKnowledgeDocumentService

    upload = await client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("manual.txt", "知识正文".encode(), "text/plain")},
    )
    status = await client.get("/api/v1/knowledge/status")

    assert upload.status_code == 201
    assert upload.json() == {"filename": "manual.txt", "node_count": 2}
    assert status.status_code == 200
    assert status.json()["node_count"] == 9
