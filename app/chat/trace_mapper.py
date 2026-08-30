from __future__ import annotations

import time
from typing import Any

from agents import AgentUpdatedStreamEvent, RunItemStreamEvent

_TOOL_LABELS = {
    "run_knowledge_agent": "正在调用知识检索 Agent",
    "run_agent2": "正在调用 agent2",
    "run_agent3": "正在调用 agent3",
    "run_agent4": "正在调用 agent4",
    "search_knowledge_base": "正在检索知识库",
}


class SafeTraceMapper:
    """Convert SDK lifecycle events into redacted, user-safe execution milestones."""

    def __init__(self, started_at: float) -> None:
        self.started_at = started_at
        self.sequence = 0
        self.seen: set[str] = set()
        self.tool_calls: dict[str, tuple[str, str]] = {}
        self.active_tools: set[tuple[str, str, str]] = set()

    def elapsed_ms(self) -> int:
        return max(0, round((time.monotonic() - self.started_at) * 1000))

    def trace(
        self,
        *,
        label: str,
        status: str,
        agent: str,
        tool: str | None = None,
        dedupe_key: str | None = None,
    ) -> dict[str, Any] | None:
        if dedupe_key is not None:
            if dedupe_key in self.seen:
                return None
            self.seen.add(dedupe_key)
        self.sequence += 1
        return {
            "type": "trace",
            "sequence": self.sequence,
            "status": status,
            "label": label,
            "agent": agent,
            "tool": tool,
            "elapsed_ms": self.elapsed_ms(),
        }

    def map(self, event: object, *, scope: str, agent_name: str) -> dict[str, Any] | None:
        if isinstance(event, AgentUpdatedStreamEvent):
            name = event.new_agent.name
            return self.trace(
                label=f"{name} 开始执行",
                status="running",
                agent=name,
                dedupe_key=f"{scope}:agent:{name}",
            )
        if not isinstance(event, RunItemStreamEvent):
            return None
        if event.name == "tool_called":
            tool_name = getattr(event.item, "tool_name", None) or "unknown_tool"
            call_id = getattr(event.item, "call_id", None) or f"{scope}:{self.sequence}"
            self.tool_calls[str(call_id)] = (str(tool_name), agent_name)
            active_key = (scope, agent_name, str(tool_name))
            if active_key in self.active_tools:
                return None
            self.active_tools.add(active_key)
            return self.trace(
                label=_TOOL_LABELS.get(str(tool_name), f"正在调用 {tool_name}"),
                status="running",
                agent=agent_name,
                tool=str(tool_name),
                dedupe_key=f"{scope}:called:{call_id}",
            )
        if event.name == "tool_output":
            call_id = getattr(event.item, "call_id", None)
            tool_name, owner = self.tool_calls.get(str(call_id), ("unknown_tool", agent_name))
            active_key = (scope, owner, tool_name)
            if active_key not in self.active_tools:
                return None
            self.active_tools.remove(active_key)
            completed = (
                "知识库检索完成"
                if tool_name == "search_knowledge_base"
                else f"{tool_name} 执行完成"
            )
            return self.trace(
                label=completed,
                status="completed",
                agent=owner,
                tool=tool_name,
                dedupe_key=f"{scope}:output:{call_id}",
            )
        if event.name == "reasoning_item_created":
            item_id = getattr(getattr(event.item, "raw_item", None), "id", self.sequence)
            return self.trace(
                label="模型已完成推理阶段",
                status="completed",
                agent=agent_name,
                dedupe_key=f"{scope}:reasoning:{item_id}",
            )
        return None


def chunk_answer(answer: str, size: int = 32) -> list[str]:
    return [answer[index : index + size] for index in range(0, len(answer), size)]
