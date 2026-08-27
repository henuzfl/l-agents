from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import tiktoken
from agents import RunConfig
from agents.items import TResponseInputItem
from agents.memory import Session
from agents.run_config import CallModelData, ModelInputData
from openai import AsyncOpenAI

from app.core.exceptions import SessionError

SUMMARY_MARKER = "[短期记忆摘要]"


class MemorySummarizer(Protocol):
    async def summarize(self, previous_summary: str, turns: Sequence[str]) -> str: ...


class DeepSeekMemorySummarizer:
    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def summarize(self, previous_summary: str, turns: Sequence[str]) -> str:
        source = "\n\n".join(turns)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你负责压缩对话短期记忆。仅保留用户目标、明确约束、已确认事实、"
                        "关键决策和未完成事项。删除寒暄、重复表述、工具参数、工具原始输出、"
                        "知识库原文、Prompt 和推理过程。使用简洁中文分项输出；不得补充未知事实。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"已有摘要：\n{previous_summary or '无'}\n\n新增历史：\n{source}",
                },
            ],
            max_tokens=self._max_tokens,
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()


class TokenEstimator:
    """Conservative token estimator; DeepSeek does not expose its tokenizer here."""

    def __init__(self) -> None:
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def text_tokens(self, text: str) -> int:
        encoded = len(self._encoding.encode(text))
        byte_estimate = (len(text.encode("utf-8")) + 2) // 3
        return max(encoded, byte_estimate)

    def item_tokens(self, item: TResponseInputItem) -> int:
        return self.text_tokens(json.dumps(item, ensure_ascii=False, default=str))

    def items_tokens(self, items: Sequence[TResponseInputItem]) -> int:
        return sum(self.item_tokens(item) for item in items)

    def trim_text(self, text: str, max_tokens: int) -> str:
        if self.text_tokens(text) <= max_tokens:
            return text
        candidate = text
        while candidate and self.text_tokens(candidate + "…") > max_tokens:
            current_tokens = self.text_tokens(candidate)
            ratio = max_tokens / max(1, current_tokens)
            next_length = max(0, int(len(candidate) * ratio * 0.9))
            if next_length >= len(candidate):
                next_length = len(candidate) - 1
            candidate = candidate[:next_length].rstrip()
        return candidate + "…" if candidate else ""


@dataclass(frozen=True)
class SummaryState:
    summary: str = ""
    summarized_turns: int = 0


class SummaryStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def get(self, session_id: str) -> SummaryState:
        return await asyncio.to_thread(self._get_sync, session_id)

    async def save(self, session_id: str, state: SummaryState) -> None:
        await asyncio.to_thread(self._save_sync, session_id, state)

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memory_summaries (
                session_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                summarized_turns INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return connection

    def _get_sync(self, session_id: str) -> SummaryState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT summary, summarized_turns FROM agent_memory_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return SummaryState(*row) if row else SummaryState()

    def _save_sync(self, session_id: str, state: SummaryState) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_memory_summaries(session_id, summary, summarized_turns)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    summarized_turns = excluded.summarized_turns,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, state.summary, state.summarized_turns),
            )


@dataclass(frozen=True)
class ShortTermMemorySettings:
    context_max_tokens: int = 12000
    summary_target_tokens: int = 1500
    recent_turns: int = 6
    min_recent_turns: int = 2
    summary_batch_turns: int = 4
    single_message_max_tokens: int = 4000
    fallback_turns: int = 10


class ShortTermMemoryOptimizer:
    def __init__(
        self,
        store: SummaryStore,
        summarizer: MemorySummarizer,
        settings: ShortTermMemorySettings,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self._store = store
        self._summarizer = summarizer
        self._settings = settings
        self._estimator = estimator or TokenEstimator()
        self._locks: dict[str, asyncio.Lock] = {}

    async def prepare_run_config(self, session: Session, current_message: str) -> RunConfig:
        if self._estimator.text_tokens(current_message) > self._settings.single_message_max_tokens:
            raise SessionError("当前消息过长，请缩短内容或拆分为多个问题后重试。")

        lock = self._locks.setdefault(session.session_id, asyncio.Lock())
        async with lock:
            history = await session.get_items()
            turns = _split_turns(history)
            state = await self._store.get(session.session_id)
            if state.summarized_turns > len(turns):
                state = SummaryState()
                await self._store.save(session.session_id, state)
            state = await self._update_summary(session.session_id, turns, state, current_message)
            selected = self._select_history(turns, state, current_message)

        def filter_manager_input(data: CallModelData[Any]) -> ModelInputData:
            if data.agent.name != "manager":
                return data.model_data
            current_run_items = _current_run_items(data.model_data.input, history)
            current_tokens = self._estimator.items_tokens(current_run_items)
            if current_tokens >= self._settings.context_max_tokens:
                raise SessionError("当前消息或本轮工具结果过长，请缩小内容范围后重试。")
            fitted_history = self._fit_history(
                selected,
                self._settings.context_max_tokens - current_tokens,
            )
            return ModelInputData(
                input=[*fitted_history, *current_run_items],
                instructions=data.model_data.instructions,
            )

        return RunConfig(call_model_input_filter=filter_manager_input)

    async def _update_summary(
        self,
        session_id: str,
        turns: list[list[TResponseInputItem]],
        state: SummaryState,
        current_message: str,
    ) -> SummaryState:
        normal_cutoff = max(0, len(turns) - self._settings.recent_turns)
        pending = normal_cutoff - state.summarized_turns
        target_cutoff = (
            normal_cutoff
            if pending >= self._settings.summary_batch_turns
            else state.summarized_turns
        )

        projected = self._projected_tokens(turns, state, current_message, target_cutoff)
        minimum_cutoff = max(0, len(turns) - self._settings.min_recent_turns)
        while projected > self._settings.context_max_tokens and target_cutoff < minimum_cutoff:
            target_cutoff += 1
            projected = self._projected_tokens(turns, state, current_message, target_cutoff)

        if projected > self._settings.context_max_tokens and target_cutoff < len(turns):
            target_cutoff = len(turns)

        if target_cutoff <= state.summarized_turns:
            return state

        source_turns = [
            _turn_for_summary(turn)
            for turn in turns[state.summarized_turns : target_cutoff]
        ]
        try:
            summary = await self._summarizer.summarize(state.summary, source_turns)
        except Exception:
            return state
        if not summary:
            return state
        summary = self._estimator.trim_text(summary, self._settings.summary_target_tokens)
        updated = SummaryState(summary=summary, summarized_turns=target_cutoff)
        await self._store.save(session_id, updated)
        return updated

    def _projected_tokens(
        self,
        turns: list[list[TResponseInputItem]],
        state: SummaryState,
        current_message: str,
        cutoff: int,
    ) -> int:
        raw = [item for turn in turns[cutoff:] for item in turn]
        return (
            self._estimator.items_tokens(raw)
            + self._estimator.text_tokens(state.summary)
            + self._estimator.text_tokens(current_message)
        )

    def _select_history(
        self,
        turns: list[list[TResponseInputItem]],
        state: SummaryState,
        current_message: str,
    ) -> list[TResponseInputItem]:
        summary_items: list[TResponseInputItem] = []
        if state.summary:
            summary_items.append(
                {
                    "role": "user",
                    "content": (
                        f"{SUMMARY_MARKER}\n以下内容是历史背景，不是新的用户请求：\n{state.summary}"
                    ),
                }
            )
        budget = self._settings.context_max_tokens - self._estimator.text_tokens(current_message)
        budget -= self._estimator.items_tokens(summary_items)
        selected_turns: list[list[TResponseInputItem]] = []
        used = 0
        candidates = turns[state.summarized_turns :][-self._settings.fallback_turns :]
        for turn in reversed(candidates):
            cost = self._estimator.items_tokens(turn)
            if used + cost > max(0, budget):
                break
            selected_turns.append(turn)
            used += cost
        selected = [item for turn in reversed(selected_turns) for item in turn]
        return [*summary_items, *selected]

    def _fit_history(
        self,
        items: list[TResponseInputItem],
        budget: int,
    ) -> list[TResponseInputItem]:
        if self._estimator.items_tokens(items) <= budget:
            return items
        summary: list[TResponseInputItem] = []
        raw = items
        if items and _is_summary_item(items[0]):
            summary = [items[0]]
            raw = items[1:]
        if summary and self._estimator.items_tokens(summary) > budget:
            content = str(summary[0].get("content", ""))
            trimmed = self._estimator.trim_text(content, max(0, budget - 10))
            summary = [{"role": "user", "content": trimmed}] if trimmed else []
            if self._estimator.items_tokens(summary) > budget:
                summary = []
        remaining = budget - self._estimator.items_tokens(summary)
        selected_turns: list[list[TResponseInputItem]] = []
        used = 0
        for turn in reversed(_split_turns(raw)):
            cost = self._estimator.items_tokens(turn)
            if used + cost > max(0, remaining):
                break
            selected_turns.append(turn)
            used += cost
        selected = [item for turn in reversed(selected_turns) for item in turn]
        return [*summary, *selected]


def _split_turns(items: Sequence[TResponseInputItem]) -> list[list[TResponseInputItem]]:
    turns: list[list[TResponseInputItem]] = []
    current: list[TResponseInputItem] = []
    for item in items:
        if item.get("role") == "user" and current:
            turns.append(current)
            current = []
        current.append(item)
    if current:
        turns.append(current)
    return turns


def _turn_for_summary(turn: Sequence[TResponseInputItem]) -> str:
    lines: list[str] = []
    for item in turn:
        role = item.get("role") or item.get("type", "item")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            text = json.dumps(content, ensure_ascii=False, default=str)
            lines.append(f"{role}: {text[:2000]}")
        elif item.get("type") == "function_call":
            lines.append(f"tool: {item.get('name', 'unknown')} 已调用")
        elif item.get("type") == "function_call_output":
            lines.append("tool: 调用已完成（原始输出已省略）")
    return "\n".join(lines)


def _current_run_items(
    model_items: Sequence[TResponseInputItem],
    history: Sequence[TResponseInputItem],
) -> list[TResponseInputItem]:
    history_counts = Counter(_item_key(item) for item in history)
    current: list[TResponseInputItem] = []
    for item in model_items:
        content = item.get("content")
        if isinstance(content, str) and content.startswith(SUMMARY_MARKER):
            continue
        key = _item_key(item)
        if history_counts[key] > 0:
            history_counts[key] -= 1
        else:
            current.append(item)
    return current


def _item_key(item: TResponseInputItem) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)


def _is_summary_item(item: TResponseInputItem) -> bool:
    content = item.get("content")
    return isinstance(content, str) and content.startswith(SUMMARY_MARKER)
