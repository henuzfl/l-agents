from pathlib import Path

import pytest

from app.core.config import Settings
from app.knowledge.store import KnowledgeChunk
from app.knowledge.uploads import (
    InvalidKnowledgeDocument,
    KnowledgeDocumentService,
    extract_document_text,
)


class FakeStore:
    nodes = []

    def __init__(self, _settings: Settings) -> None:
        pass

    def add_nodes(self, nodes):  # type: ignore[no-untyped-def]
        FakeStore.nodes = nodes
        return len(nodes)

    def delete_document(self, _object_name: str) -> None:
        FakeStore.nodes = []

    def list_document_chunks(
        self,
        object_name: str,
        **_filters: object,
    ) -> tuple[int, list[KnowledgeChunk]]:
        chunks = [
            KnowledgeChunk(node.node_id, node.text, dict(node.metadata))
            for node in FakeStore.nodes
            if node.metadata.get("minio_object") == object_name
        ]
        return len(chunks), chunks

    def get_document_chunk(self, object_name: str, node_id: str) -> KnowledgeChunk | None:
        return next(
            (
                KnowledgeChunk(node.node_id, node.text, dict(node.metadata))
                for node in FakeStore.nodes
                if node.metadata.get("minio_object") == object_name and node.node_id == node_id
            ),
            None,
        )


class FakeObjectStorage:
    bucket = "knowledge-documents"
    objects: dict[str, bytes] = {}

    def __init__(self) -> None:
        self.objects = {}
        FakeObjectStorage.objects = self.objects

    def upload(self, object_name: str, content: bytes, _content_type: str) -> None:
        self.objects[object_name] = content

    def download(self, object_name: str) -> bytes:
        return self.objects[object_name]

    def delete(self, object_name: str) -> None:
        self.objects.pop(object_name)

    def delete_assets(self, object_name: str) -> None:
        prefix = f"{object_name.rsplit('/', 1)[0]}/assets/"
        for name in [name for name in self.objects if name.startswith(prefix)]:
            self.objects.pop(name)


def build_service(tmp_path: Path, **settings: object) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        Settings(
            sqlite_session_path=tmp_path / "sessions.db",
            knowledge_registry_path=tmp_path / "knowledge.db",
            **settings,
        ),
        store_factory=FakeStore,
        object_storage=FakeObjectStorage(),  # type: ignore[arg-type]
    )


def test_extracts_utf8_text_document() -> None:
    assert extract_document_text("guide.md", "# 使用说明".encode()) == "# 使用说明"


def test_rejects_unsupported_or_empty_document() -> None:
    with pytest.raises(InvalidKnowledgeDocument, match="不支持"):
        extract_document_text("data.csv", b"a,b")
    with pytest.raises(InvalidKnowledgeDocument, match="没有可提取"):
        extract_document_text("empty.txt", b"  ")


def test_upload_saves_raw_file_before_background_processing(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    job = service.start_upload("../manual.txt", "知识正文".encode(), "text/plain")

    assert job.filename == "manual.txt"
    assert job.loading.state == "completed"
    assert job.chunking.state == "pending"
    assert FakeObjectStorage.objects[job.object_name] == "知识正文".encode()

    service.process(job.task_id)
    completed = service.get_job(job.task_id)
    assert completed.status == "completed"
    assert completed.chunking.state == "completed"
    assert completed.embedding.state == "completed"
    assert completed.chunk_count == len(FakeStore.nodes)
    assert FakeStore.nodes[0].metadata["minio_object"] == job.object_name
    relation = service.list_chunks(job.task_id)
    assert relation["minio_object"] == job.object_name
    assert relation["total"] == completed.chunk_count
    assert relation["chunks"][0]["minio_object"] == job.object_name  # type: ignore[index]


def test_upload_enforces_configured_size_limit(tmp_path: Path) -> None:
    service = build_service(tmp_path, knowledge_upload_max_bytes=3)
    with pytest.raises(InvalidKnowledgeDocument, match="不能超过"):
        service.start_upload("manual.txt", b"1234", "text/plain")


def test_registry_survives_service_recreation_and_delete_cleans_sources(tmp_path: Path) -> None:
    storage = FakeObjectStorage()
    settings = Settings(
        sqlite_session_path=tmp_path / "sessions.db",
        knowledge_registry_path=tmp_path / "knowledge.db",
    )
    service = KnowledgeDocumentService(
        settings,
        store_factory=FakeStore,
        object_storage=storage,  # type: ignore[arg-type]
    )
    job = service.start_upload("manual.txt", b"knowledge", "text/plain")
    service.process(job.task_id)

    recreated = KnowledgeDocumentService(
        settings,
        store_factory=FakeStore,
        object_storage=storage,  # type: ignore[arg-type]
    )
    assert recreated.get_job(job.task_id).filename == "manual.txt"
    assert recreated.download(job.task_id)[2] == b"knowledge"

    recreated.delete(job.task_id)
    assert recreated.list_jobs() == []
    assert storage.objects == {}


def test_download_asset_requires_a_chunk_owned_by_the_document(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    job = service.start_upload("manual.md", b"# Knowledge", "text/markdown")
    service.process(job.task_id)
    node = FakeStore.nodes[0]
    asset_name = f"{job.object_name.rsplit('/', 1)[0]}/assets/diagram.png"
    node.metadata["asset_object"] = asset_name
    FakeObjectStorage.objects[asset_name] = b"image-content"

    filename, content_type, content = service.download_asset(job.task_id, node.node_id)

    assert filename == "diagram.png"
    assert content_type == "image/png"
    assert content == b"image-content"
    with pytest.raises(KeyError):
        service.download_asset(job.task_id, "missing-node")


def test_service_restart_marks_interrupted_job_reprocessable(tmp_path: Path) -> None:
    storage = FakeObjectStorage()
    settings = Settings(
        sqlite_session_path=tmp_path / "sessions.db",
        knowledge_registry_path=tmp_path / "knowledge.db",
    )
    service = KnowledgeDocumentService(
        settings,
        store_factory=FakeStore,
        object_storage=storage,  # type: ignore[arg-type]
    )
    job = service.start_upload("manual.txt", b"knowledge", "text/plain")

    recreated = KnowledgeDocumentService(
        settings,
        store_factory=FakeStore,
        object_storage=storage,  # type: ignore[arg-type]
    )
    interrupted = recreated.get_job(job.task_id)
    assert interrupted.status == "failed"
    assert "重新处理" in (interrupted.error or "")
    asset_name = f"{job.object_name.rsplit('/', 1)[0]}/assets/image.png"
    storage.objects[asset_name] = b"old image"
    assert recreated.restart(job.task_id).status == "processing"
    assert asset_name not in storage.objects
