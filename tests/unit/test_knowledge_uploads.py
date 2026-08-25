from pathlib import Path

import pytest

from app.core.config import Settings
from app.knowledge.uploads import (
    InvalidKnowledgeDocument,
    KnowledgeDocumentService,
    extract_document_text,
)


class FakeStore:
    document = None

    def __init__(self, _settings: Settings) -> None:
        pass

    def add_document(self, document):  # type: ignore[no-untyped-def]
        FakeStore.document = document
        return 3


def test_extracts_utf8_text_document() -> None:
    assert extract_document_text("guide.md", "# 使用说明".encode()) == "# 使用说明"


def test_rejects_unsupported_or_empty_document() -> None:
    with pytest.raises(InvalidKnowledgeDocument, match="不支持"):
        extract_document_text("data.csv", b"a,b")
    with pytest.raises(InvalidKnowledgeDocument, match="没有可提取"):
        extract_document_text("empty.txt", b"  ")


def test_upload_adds_filename_metadata_without_saving_file(tmp_path: Path) -> None:
    service = KnowledgeDocumentService(
        Settings(sqlite_session_path=tmp_path / "sessions.db"),
        store_factory=FakeStore,
    )
    result = service.upload("../manual.txt", "知识正文".encode())

    assert result == {"filename": "manual.txt", "node_count": 3}
    assert FakeStore.document.metadata == {"source": "manual.txt", "section": "上传文档"}
    assert FakeStore.document.text == "知识正文"


def test_upload_enforces_configured_size_limit(tmp_path: Path) -> None:
    service = KnowledgeDocumentService(
        Settings(
            sqlite_session_path=tmp_path / "sessions.db",
            knowledge_upload_max_bytes=3,
        ),
        store_factory=FakeStore,
    )
    with pytest.raises(InvalidKnowledgeDocument, match="不能超过"):
        service.upload("manual.txt", b"1234")
