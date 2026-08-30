from __future__ import annotations

import base64
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal

import pymupdf
import pymupdf4llm
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, TextNode
from openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError

ElementType = Literal["text", "table", "code", "image", "scanned_page"]
AssetUploader = Callable[[str, bytes, str], None]


@dataclass
class ParsedElement:
    element_type: ElementType
    page_number: int
    text: str
    language: str | None = None
    asset_object: str | None = None


@dataclass
class PdfProcessingResult:
    nodes: list[BaseNode]
    warnings: list[str] = field(default_factory=list)
    element_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class VisionResult:
    ocr_text: str
    description: str
    tables: list[str]
    code_blocks: list[tuple[str, str]]


class QwenVisionAnalyzer:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        base_url = settings.qwen_vision_base_url or settings.qwen_embedding_base_url
        if not base_url:
            raise KnowledgeConfigurationError("缺少视觉模型配置：QWEN_VISION_BASE_URL")
        if settings.dashscope_api_key is None:
            raise KnowledgeConfigurationError("缺少视觉模型配置：DASHSCOPE_API_KEY")
        self._model = settings.qwen_vision_model
        self._client = client or OpenAI(
            api_key=settings.dashscope_api_key.get_secret_value(),
            base_url=base_url,
            timeout=60.0,
            max_retries=2,
        )

    def analyze(self, image: bytes, context: str) -> VisionResult:
        encoded = base64.b64encode(image).decode("ascii")
        prompt = (
            f"你正在分析 PDF 中的{context}。请同时完成 OCR 和视觉理解。"
            "仅返回 JSON 对象，字段为：ocr_text（完整可读文字）、description（图表、流程、"
            "截图或布局的简洁说明）、tables（Markdown 表格字符串数组）、code_blocks"
            "（对象数组，每项包含 language 和 code）。不要臆造不可见内容。"
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = self._parse_json(content)
        code_blocks = [
            (str(item.get("language", "text")), str(item.get("code", "")))
            for item in payload.get("code_blocks", [])
            if isinstance(item, dict) and str(item.get("code", "")).strip()
        ]
        return VisionResult(
            ocr_text=str(payload.get("ocr_text", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            tables=[str(item).strip() for item in payload.get("tables", []) if str(item).strip()],
            code_blocks=code_blocks,
        )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = content.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            payload = json.loads(match.group(0)) if match else {}
        return payload if isinstance(payload, dict) else {}


def split_structured_markdown(markdown: str, page_number: int) -> list[ParsedElement]:
    lines = markdown.splitlines()
    elements: list[ParsedElement] = []
    text_buffer: list[str] = []

    def flush_text() -> None:
        text = "\n".join(text_buffer).strip()
        if text:
            elements.append(ParsedElement("text", page_number, text))
        text_buffer.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            flush_text()
            language = line.lstrip()[3:].strip() or "text"
            code_lines: list[str] = []
            index += 1
            nested_language = (
                lines[index].lstrip()[3:].strip()
                if (
                    language == "text"
                    and index < len(lines)
                    and lines[index].lstrip().startswith("```")
                )
                else ""
            )
            if nested_language:
                language = nested_language
                index += 1
                while index < len(lines) and not lines[index].lstrip().startswith("```"):
                    code_lines.append(lines[index])
                    index += 1
                code = "\n".join(code_lines).strip()
                if code:
                    elements.append(ParsedElement("code", page_number, code, language=language))
                index += 1
                while index < len(lines) and not lines[index].strip():
                    index += 1
                if index < len(lines) and lines[index].lstrip().startswith("```"):
                    index += 1
                continue
            while index < len(lines) and not lines[index].lstrip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            code = "\n".join(code_lines).strip()
            if code:
                elements.append(ParsedElement("code", page_number, code, language=language))
        elif _is_table_start(lines, index):
            flush_text()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            elements.append(ParsedElement("table", page_number, "\n".join(table_lines)))
            continue
        else:
            text_buffer.append(line)
        index += 1
    flush_text()
    return elements


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    separator = lines[index + 1].strip().strip("|")
    cells = [cell.strip() for cell in separator.split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def process_pdf(
    content: bytes,
    filename: str,
    source_object: str,
    settings: Settings,
    upload_asset: AssetUploader,
    vision: QwenVisionAnalyzer | None = None,
) -> PdfProcessingResult:
    analyzer = vision or QwenVisionAnalyzer(settings)
    document = pymupdf.open(stream=content, filetype="pdf")
    page_chunks = pymupdf4llm.to_markdown(
        document,
        page_chunks=True,
        use_ocr=False,
        header=False,
        footer=False,
        ignore_code=False,
        show_progress=False,
    )
    elements: list[ParsedElement] = []
    warnings: list[str] = []
    image_candidates: list[tuple[int, bytes, str]] = []
    scanned_count = 0

    for page_index, page in enumerate(document):
        page_number = page_index + 1
        native_text = page.get_text("text").strip()
        markdown = str(page_chunks[page_index].get("text", ""))
        if len(native_text) < 30 and scanned_count < settings.qwen_vision_max_pages:
            scanned_count += 1
            page_png = page.get_pixmap(dpi=180, alpha=False).tobytes("png")
            try:
                result = analyzer.analyze(page_png, f"第 {page_number} 页扫描页面")
                elements.extend(_vision_elements(result, page_number, "scanned_page"))
            except Exception:
                warnings.append(f"第 {page_number} 页视觉识别失败，已跳过扫描内容。")
        else:
            if len(native_text) < 30:
                warnings.append(
                    f"扫描页超过 {settings.qwen_vision_max_pages} 页上限，后续页面已跳过。"
                )
            elements.extend(split_structured_markdown(markdown, page_number))
            image_candidates.extend(_page_image_candidates(page, page_number))

    hashes = [digest for _, _, digest in image_candidates]
    repeated = {digest for digest, count in Counter(hashes).items() if count >= 3}
    processed_hashes: set[str] = set()
    image_count = 0
    asset_prefix = source_object.rsplit("/", 1)[0]
    for page_number, image, digest in image_candidates:
        if digest in repeated or digest in processed_hashes:
            continue
        if image_count >= settings.qwen_vision_max_images:
            warnings.append(
                f"有效图片超过 {settings.qwen_vision_max_images} 张上限，剩余图片已跳过。"
            )
            break
        processed_hashes.add(digest)
        image_count += 1
        asset_object = f"{asset_prefix}/assets/page-{page_number}-image-{image_count}.png"
        upload_asset(asset_object, image, "image/png")
        try:
            result = analyzer.analyze(image, f"第 {page_number} 页正文图片")
            image_elements = _vision_elements(result, page_number, "image")
            for element in image_elements:
                element.asset_object = asset_object
            elements.extend(image_elements)
        except Exception:
            warnings.append(f"第 {page_number} 页第 {image_count} 张图片理解失败。")

    document.close()
    nodes = _elements_to_nodes(elements, filename, source_object)
    if not nodes:
        raise ValueError("PDF 中没有可提取或识别的内容。")
    counts = Counter(element.element_type for element in elements if element.text.strip())
    counts["assets"] = image_count
    return PdfProcessingResult(nodes, warnings, dict(counts))


def _page_image_candidates(page: pymupdf.Page, page_number: int) -> list[tuple[int, bytes, str]]:
    candidates: list[tuple[int, bytes, str]] = []
    page_area = max(page.rect.width * page.rect.height, 1)
    for info in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(info["bbox"])
        width = int(info.get("width", 0))
        height = int(info.get("height", 0))
        area_ratio = max(bbox.width * bbox.height, 0) / page_area
        if width < 160 or height < 120 or area_ratio < 0.02:
            continue
        pixmap = page.get_pixmap(clip=bbox, dpi=150, alpha=False)
        image = pixmap.tobytes("png")
        raw_digest = info.get("digest")
        digest = raw_digest.hex() if isinstance(raw_digest, bytes) else sha256(image).hexdigest()
        candidates.append((page_number, image, digest))
    return candidates


def _vision_elements(
    result: VisionResult,
    page_number: int,
    base_type: Literal["image", "scanned_page"],
) -> list[ParsedElement]:
    elements: list[ParsedElement] = []
    combined = "\n\n".join(part for part in (result.ocr_text, result.description) if part)
    if combined:
        elements.append(ParsedElement(base_type, page_number, combined))
    elements.extend(ParsedElement("table", page_number, table) for table in result.tables)
    elements.extend(
        ParsedElement("code", page_number, code, language=language)
        for language, code in result.code_blocks
    )
    return elements


def _elements_to_nodes(
    elements: list[ParsedElement],
    filename: str,
    source_object: str,
) -> list[BaseNode]:
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=80)
    nodes: list[BaseNode] = []
    for element_index, element in enumerate(elements, start=1):
        if not element.text.strip():
            continue
        parts = _split_element(element, splitter)
        for part_index, part in enumerate(parts, start=1):
            metadata: dict[str, Any] = {
                "source": filename,
                "section": f"第 {element.page_number} 页",
                "page_number": element.page_number,
                "element_type": element.element_type,
                "element_index": element_index,
                "element_part": part_index,
                "minio_object": source_object,
            }
            if element.language:
                metadata["language"] = element.language
            if element.asset_object:
                metadata["asset_object"] = element.asset_object
            nodes.append(TextNode(text=part, metadata=metadata))
    return nodes


def _split_element(element: ParsedElement, splitter: SentenceSplitter) -> list[str]:
    if element.element_type == "table":
        return _split_table(element.text)
    if element.element_type == "code":
        return _split_code(element.text, element.language or "text")
    return splitter.split_text(element.text)


def _split_table(table: str, max_chars: int = 1800) -> list[str]:
    lines = [line for line in table.splitlines() if line.strip()]
    if len(table) <= max_chars or len(lines) <= 2:
        return [table]
    header = lines[:2]
    groups: list[str] = []
    current = header.copy()
    for row in lines[2:]:
        candidate = "\n".join([*current, row])
        if len(candidate) > max_chars and len(current) > 2:
            groups.append("\n".join(current))
            current = [*header, row]
        else:
            current.append(row)
    if len(current) > 2:
        groups.append("\n".join(current))
    return groups


def _split_code(code: str, language: str, max_chars: int = 2400) -> list[str]:
    if len(code) <= max_chars:
        return [f"```{language}\n{code}\n```"]
    groups: list[str] = []
    current: list[str] = []
    for line in code.splitlines():
        if current and len("\n".join([*current, line])) > max_chars:
            joined = "\n".join(current)
            groups.append(f"```{language}\n{joined}\n```")
            current = [line]
        else:
            current.append(line)
    if current:
        joined = "\n".join(current)
        groups.append(f"```{language}\n{joined}\n```")
    return groups
