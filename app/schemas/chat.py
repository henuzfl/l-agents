from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatRequest(BaseModel):
    conversation_id: NonEmptyString
    message: NonEmptyString


class KnowledgeEvidence(BaseModel):
    node_id: str
    source: str
    section: str
    page_number: int | None = None
    element_type: str = "text"
    element_index: int | None = None
    element_part: int | None = None
    language: str | None = None
    content: str = ""
    score: float | None = None
    minio_object: str | None = None
    task_id: str | None = None
    asset_url: str | None = None
    download_url: str | None = None


class ChatResponse(BaseModel):
    conversation_id: NonEmptyString
    answer: NonEmptyString
    evidence: list[KnowledgeEvidence] = Field(default_factory=list)
