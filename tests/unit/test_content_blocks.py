from app.chat.content_blocks import build_answer_content


def image_evidence(node_id: str, page_number: int) -> dict[str, object]:
    return {
        "node_id": node_id,
        "source": "manual.pdf",
        "section": f"第 {page_number} 页",
        "page_number": page_number,
        "element_type": "image",
        "content": f"第 {page_number} 页流程图",
        "asset_url": f"/api/v1/knowledge/documents/task/chunks/{node_id}/asset",
    }


def test_build_answer_content_places_valid_image_between_markdown() -> None:
    answer, blocks = build_answer_content(
        "前文。\n\n[[kb-image:image-1]]\n\n后文。",
        [image_evidence("image-1", 2)],
    )

    assert answer == "前文。\n\n后文。"
    assert [block["type"] for block in blocks] == ["markdown", "image", "markdown"]
    assert blocks[1]["node_id"] == "image-1"
    assert blocks[1]["page_number"] == 2


def test_build_answer_content_removes_untrusted_and_non_image_markers() -> None:
    evidence = [
        image_evidence("image-1", 2),
        {
            "node_id": "text-1",
            "source": "manual.pdf",
            "section": "第 1 页",
            "element_type": "text",
            "content": "正文",
            "asset_url": "/api/v1/knowledge/documents/task/chunks/text-1/asset",
        },
    ]
    answer, blocks = build_answer_content(
        "正文。[[kb-image:text-1]][[kb-image:forged-node]]",
        evidence,
    )

    assert answer == "正文。"
    assert [block["type"] for block in blocks] == ["markdown"]
    assert "kb-image" not in str(blocks)


def test_build_answer_content_rejects_images_that_break_source_order() -> None:
    evidence = [image_evidence("image-1", 1), image_evidence("image-2", 2)]
    answer, blocks = build_answer_content(
        "第二张。[[kb-image:image-2]]\n\n第一张。[[kb-image:image-1]]",
        evidence,
    )

    assert answer == "第二张。\n\n第一张。"
    assert [block["type"] for block in blocks] == ["markdown", "markdown"]

