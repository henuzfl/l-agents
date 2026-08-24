from app.api.routes.chat import encode_sse


def test_sse_encoder_uses_named_events_and_utf8_json() -> None:
    encoded = encode_sse({"type": "trace", "label": "正在检索知识库"})

    assert encoded.startswith("event: trace\n")
    assert 'data: {"type":"trace","label":"正在检索知识库"}\n\n' in encoded


def test_sse_encoder_formats_heartbeat_as_comment() -> None:
    assert encode_sse({"type": "heartbeat"}) == ": heartbeat\n\n"
