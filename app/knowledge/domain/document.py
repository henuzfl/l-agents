from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

StageState = Literal["pending", "running", "completed", "failed"]
JobState = Literal["processing", "completed", "failed"]


@dataclass
class PipelineStage:
    state: StageState = "pending"
    detail: str = "等待处理"


@dataclass
class DocumentJob:
    task_id: str
    filename: str
    object_name: str
    status: JobState
    loading: PipelineStage
    chunking: PipelineStage
    embedding: PipelineStage
    chunk_count: int | None
    created_at: str
    updated_at: str
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    element_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> DocumentJob:
        data = dict(payload)
        data.setdefault("warnings", [])
        data.setdefault("element_counts", {})
        data["loading"] = PipelineStage(**data["loading"])  # type: ignore[arg-type]
        data["chunking"] = PipelineStage(**data["chunking"])  # type: ignore[arg-type]
        data["embedding"] = PipelineStage(**data["embedding"])  # type: ignore[arg-type]
        return cls(**data)  # type: ignore[arg-type]
