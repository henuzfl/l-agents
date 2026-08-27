from io import BytesIO

import pymupdf
from PIL import Image

from app.core.config import Settings
from app.knowledge.pdf_processing import (
    QwenVisionAnalyzer,
    VisionResult,
    process_pdf,
    split_structured_markdown,
)


class FakeVisionAnalyzer:
    def analyze(self, _image: bytes, _context: str) -> VisionResult:
        return VisionResult(
            ocr_text="扫描页文字",
            description="一张系统架构示意图",
            tables=["| 名称 | 数量 |\n| --- | --- |\n| Agent | 4 |"],
            code_blocks=[("python", "print('ok')")],
        )


def test_structured_markdown_preserves_table_and_code_blocks() -> None:
    elements = split_structured_markdown(
        "说明文字\n\n| 名称 | 数量 |\n| --- | --- |\n| Agent | 4 |\n\n"
        "```python\nprint('ok')\n```",
        page_number=2,
    )

    assert [element.element_type for element in elements] == ["text", "table", "code"]
    assert elements[1].page_number == 2
    assert elements[2].language == "python"
    assert elements[2].text == "print('ok')"


def test_blank_pdf_page_uses_vision_and_builds_typed_nodes() -> None:
    document = pymupdf.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    uploaded_assets: list[str] = []

    result = process_pdf(
        content,
        "manual.pdf",
        "2026/task/manual.pdf",
        Settings(),
        lambda name, _content, _type: uploaded_assets.append(name),
        vision=FakeVisionAnalyzer(),  # type: ignore[arg-type]
    )

    element_types = {node.metadata["element_type"] for node in result.nodes}
    assert element_types == {"scanned_page", "table", "code"}
    assert result.element_counts["scanned_page"] == 1
    assert uploaded_assets == []


def test_repeated_pdf_image_is_uploaded_and_analyzed_once() -> None:
    image_buffer = BytesIO()
    Image.new("RGB", (320, 240), "navy").save(image_buffer, format="PNG")
    image = image_buffer.getvalue()
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 50), "Native text keeps this page out of scanned-page processing.")
    page.insert_image(pymupdf.Rect(50, 100, 250, 250), stream=image)
    page.insert_image(pymupdf.Rect(300, 100, 500, 250), stream=image)
    content = document.tobytes()
    document.close()
    uploaded_assets: list[str] = []

    result = process_pdf(
        content,
        "duplicate-image.pdf",
        "2026/task/duplicate-image.pdf",
        Settings(),
        lambda name, _content, _type: uploaded_assets.append(name),
        vision=FakeVisionAnalyzer(),  # type: ignore[arg-type]
    )

    assert result.element_counts["assets"] == 1
    assert result.element_counts["image"] == 1
    assert len(uploaded_assets) == 1


def test_vision_json_parser_accepts_fenced_response() -> None:
    payload = QwenVisionAnalyzer._parse_json(
        '```json\n{"ocr_text":"hello","description":"diagram"}\n```'
    )
    assert payload["ocr_text"] == "hello"
