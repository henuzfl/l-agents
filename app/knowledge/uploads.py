from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from llama_index.core import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings

from .store import KnowledgeStatus, LlamaIndexKnowledgeStore

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


class InvalidKnowledgeDocument(ValueError):
    pass


StoreFactory = Callable[[Settings], LlamaIndexKnowledgeStore]


def extract_document_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        allowed = "、".join(sorted(SUPPORTED_EXTENSIONS))
        raise InvalidKnowledgeDocument(f"不支持该文件类型，可上传：{allowed}")
    try:
        if suffix in {".txt", ".md", ".markdown"}:
            text = content.decode("utf-8-sig")
        elif suffix == ".pdf":
            pages = PdfReader(BytesIO(content)).pages
            text = "\n".join(page.extract_text() or "" for page in pages)
        else:
            document = DocxDocument(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    except (
        BadZipFile,
        KeyError,
        PackageNotFoundError,
        PdfReadError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise InvalidKnowledgeDocument("无法解析文档，请确认文件未损坏且内容格式正确。") from exc
    cleaned = text.strip()
    if not cleaned:
        raise InvalidKnowledgeDocument("文档中没有可提取的文本。")
    return cleaned


class KnowledgeDocumentService:
    def __init__(
        self,
        settings: Settings,
        store_factory: StoreFactory = LlamaIndexKnowledgeStore,
    ) -> None:
        self._settings = settings
        self._store_factory = store_factory

    @property
    def max_upload_bytes(self) -> int:
        return self._settings.knowledge_upload_max_bytes

    def upload(self, filename: str, content: bytes) -> dict[str, int | str]:
        if not filename.strip():
            raise InvalidKnowledgeDocument("文件名不能为空。")
        if len(content) > self._settings.knowledge_upload_max_bytes:
            limit_mb = self._settings.knowledge_upload_max_bytes // (1024 * 1024)
            raise InvalidKnowledgeDocument(f"文件不能超过 {limit_mb} MB。")
        text = extract_document_text(filename, content)
        document = Document(
            text=text,
            metadata={"source": Path(filename).name, "section": "上传文档"},
        )
        node_count = self._store_factory(self._settings).add_document(document)
        return {"filename": Path(filename).name, "node_count": node_count}

    def status(self) -> dict[str, int | str]:
        status: KnowledgeStatus = self._store_factory(self._settings).status()
        return asdict(status)
