from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from agents import Agent, SQLiteSession
from agents.run_config import CallModelData, ModelInputData

from app.core.exceptions import SessionError
from app.memory.short_term import (
    SUMMARY_MARKER,
    ShortTermMemoryOptimizer,
    ShortTermMemorySettings,
    SummaryState,
)


class InMemorySummaryStore:
    def __init__(self) -> None:
        self.states: dict[str, SummaryState] = {}

    async def get(self, session_id: str) -> SummaryState:
        return self.states.get(session_id, SummaryState())

    async def save(self, session_id: str, state: SummaryState) -> None:
        self.states[session_id] = state


class FakeSummarizer:
    def __init__(self, result: str = "目标：维护项目；未完成：继续测试") -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    async def summarize(self, previous_summary: str, turns: Sequence[str]) -> str:
        self.calls.append((previous_summary, list(turns)))
        return self.result


class FailingSummarizer(FakeSummarizer):
    async def summarize(self, previous_summary: str, turns: Sequence[str]) -> str:
        raise RuntimeError("model unavailable")


def _settings(**overrides: int) -> ShortTermMemorySettings:
    values = {
        "context_max_tokens": 12000,
        "summary_target_tokens": 1500,
        "recent_turns": 6,
        "min_recent_turns": 2,
        "summary_batch_turns": 4,
        "single_message_max_tokens": 4000,
    }
    values.update(overrides)
    return ShortTermMemorySettings(**values)


async def _session_with_turns(database: Path, count: int) -> SQLiteSession:
    session = SQLiteSession("user:conversation", database)
    items = []
    for index in range(count):
        items.extend(
            [
                {"role": "user", "content": f"问题 {index}"},
                {"role": "assistant", "content": f"回答 {index}"},
            ]
        )
    await session.add_items(items)
    return session


def _apply_filter(run_config, history, new_items):  # type: ignore[no-untyped-def]
    callback = run_config.call_model_input_filter
    assert callback is not None
    data = CallModelData(
        model_data=ModelInputData(input=[*history, *new_items], instructions="system"),
        agent=Agent(name="manager", model="test-model"),
        context=None,
    )
    return callback(data)


@pytest.mark.asyncio
async def test_keeps_short_history_without_summarizing(tmp_path: Path) -> None:
    session = await _session_with_turns(tmp_path / "sessions.db", 3)
    summarizer = FakeSummarizer()
    optimizer = ShortTermMemoryOptimizer(
        InMemorySummaryStore(), summarizer, _settings()
    )

    config = await optimizer.prepare_run_config(session, "当前问题")
    history = await session.get_items()
    filtered = _apply_filter(config, history, [{"role": "user", "content": "当前问题"}])

    assert filtered.input == [*history, {"role": "user", "content": "当前问题"}]
    assert summarizer.calls == []


@pytest.mark.asyncio
async def test_summarizes_old_turns_and_keeps_six_recent_turns(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = await _session_with_turns(database, 10)
    summarizer = FakeSummarizer()
    store = InMemorySummaryStore()
    optimizer = ShortTermMemoryOptimizer(store, summarizer, _settings())

    config = await optimizer.prepare_run_config(session, "继续")
    history = await session.get_items()
    filtered = _apply_filter(config, history, [{"role": "user", "content": "继续"}])
    state = await store.get(session.session_id)

    assert state.summarized_turns == 4
    assert len(summarizer.calls) == 1
    assert len(summarizer.calls[0][1]) == 4
    assert filtered.input[0]["content"].startswith(SUMMARY_MARKER)
    assert filtered.input[1]["content"] == "问题 4"
    assert filtered.input[-1]["content"] == "继续"
    assert len(filtered.input) == 14


@pytest.mark.asyncio
async def test_summary_source_omits_raw_tool_output(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = SQLiteSession("user:tools", database)
    items = []
    for index in range(5):
        items.extend(
            [
                {"role": "user", "content": f"问题 {index}"},
                {
                    "type": "function_call",
                    "name": "search_knowledge_base",
                    "arguments": "SECRET ARGUMENTS",
                    "call_id": f"call-{index}",
                },
                {
                    "type": "function_call_output",
                    "call_id": f"call-{index}",
                    "output": "SECRET RAW KNOWLEDGE",
                },
                {"role": "assistant", "content": f"结论 {index}"},
            ]
        )
    await session.add_items(items)
    summarizer = FakeSummarizer()
    optimizer = ShortTermMemoryOptimizer(
        InMemorySummaryStore(), summarizer, _settings(recent_turns=1)
    )

    await optimizer.prepare_run_config(session, "继续")
    summary_source = str(summarizer.calls)

    assert "search_knowledge_base 已调用" in summary_source
    assert "SECRET ARGUMENTS" not in summary_source
    assert "SECRET RAW KNOWLEDGE" not in summary_source


@pytest.mark.asyncio
async def test_oversized_context_is_compacted_beyond_normal_window(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = await _session_with_turns(database, 6)
    summarizer = FakeSummarizer(result="压缩后的上下文")
    store = InMemorySummaryStore()
    optimizer = ShortTermMemoryOptimizer(
        store,
        summarizer,
        _settings(context_max_tokens=60, single_message_max_tokens=20),
    )

    config = await optimizer.prepare_run_config(session, "继续")
    history = await session.get_items()
    filtered = _apply_filter(config, history, [{"role": "user", "content": "继续"}])
    state = await store.get(session.session_id)

    assert state.summarized_turns == 6
    assert filtered.input[0]["content"].startswith(SUMMARY_MARKER)
    assert filtered.input[-1]["content"] == "继续"
    assert all(item.get("content") != "问题 0" for item in filtered.input)


@pytest.mark.asyncio
async def test_summary_failure_preserves_request_with_recent_history(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = await _session_with_turns(database, 10)
    store = InMemorySummaryStore()
    optimizer = ShortTermMemoryOptimizer(store, FailingSummarizer(), _settings())

    config = await optimizer.prepare_run_config(session, "继续")
    history = await session.get_items()
    filtered = _apply_filter(config, history, [{"role": "user", "content": "继续"}])

    assert (await store.get(session.session_id)).summary == ""
    assert filtered.input[-1]["content"] == "继续"
    assert len(filtered.input) > 1


@pytest.mark.asyncio
async def test_rejects_oversized_current_message(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = await _session_with_turns(database, 1)
    optimizer = ShortTermMemoryOptimizer(
        InMemorySummaryStore(), FakeSummarizer(), _settings(single_message_max_tokens=2)
    )

    with pytest.raises(SessionError, match="当前消息过长"):
        await optimizer.prepare_run_config(session, "这是明显过长的当前消息")


@pytest.mark.asyncio
async def test_rejects_current_run_tool_output_that_exceeds_budget(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = await _session_with_turns(database, 1)
    optimizer = ShortTermMemoryOptimizer(
        InMemorySummaryStore(),
        FakeSummarizer(),
        _settings(context_max_tokens=30, single_message_max_tokens=10),
    )
    config = await optimizer.prepare_run_config(session, "继续")
    history = await session.get_items()

    with pytest.raises(SessionError, match="工具结果过长"):
        _apply_filter(
            config,
            history,
            [
                {"role": "user", "content": "继续"},
                {
                    "type": "function_call_output",
                    "call_id": "call-large",
                    "output": "很长的工具输出" * 100,
                },
            ],
        )
