from __future__ import annotations

import re
from typing import Any, TypedDict

from app.knowledge.retrieval.events import EvidenceItem

IMAGE_MARKER_PATTERN = re.compile(r"\[\[kb-image:([^\]\r\n]{1,256})\]\]")


class AnswerContentBlock(TypedDict, total=False):
    type: str
    content: str
    node_id: str
    asset_url: str
    caption: str
    source: str
    page_number: int | None


def _image_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return [
        item
        for item in items
        if item.get("element_type") == "image"
        and item.get("node_id")
        and item.get("asset_url")
    ]


def _clean_answer(answer: str) -> str:
    without_markers = IMAGE_MARKER_PATTERN.sub("", answer)
    return re.sub(r"\n{3,}", "\n\n", without_markers).strip()


def _page_number(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_answer_content(
    answer: str,
    evidence: list[EvidenceItem],
) -> tuple[str, list[AnswerContentBlock]]:
    """Turn validated knowledge-image markers into ordered answer content blocks."""
    cleaned_answer = _clean_answer(answer)
    images = _image_evidence(evidence)
    by_node = {str(item["node_id"]): item for item in images}
    source_rank = {str(item["node_id"]): index for index, item in enumerate(images)}
    matches = list(IMAGE_MARKER_PATTERN.finditer(answer))

    referenced_nodes: list[str] = []
    for match in matches:
        node_id = match.group(1).strip()
        if node_id in by_node and node_id not in referenced_nodes:
            referenced_nodes.append(node_id)
    ranks = [source_rank[node_id] for node_id in referenced_nodes]
    allow_inline_images = ranks == sorted(ranks)

    blocks: list[AnswerContentBlock] = []
    used: set[str] = set()
    cursor = 0
    for match in matches:
        markdown = answer[cursor : match.start()].strip()
        if markdown:
            blocks.append({"type": "markdown", "content": markdown})

        node_id = match.group(1).strip()
        item = by_node.get(node_id)
        if allow_inline_images and item is not None and node_id not in used:
            used.add(node_id)
            blocks.append(
                {
                    "type": "image",
                    "node_id": node_id,
                    "asset_url": str(item["asset_url"]),
                    "caption": str(item.get("content") or ""),
                    "source": str(item.get("source") or "未知文档"),
                    "page_number": _page_number(item.get("page_number")),
                }
            )
        cursor = match.end()

    tail = answer[cursor:].strip()
    if tail:
        blocks.append({"type": "markdown", "content": tail})
    if not blocks and cleaned_answer:
        blocks.append({"type": "markdown", "content": cleaned_answer})
    return cleaned_answer, blocks


__all__ = ["AnswerContentBlock", "IMAGE_MARKER_PATTERN", "build_answer_content"]
