from typing import Annotated

from pydantic import BaseModel, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatRequest(BaseModel):
    user_id: NonEmptyString
    conversation_id: NonEmptyString
    message: NonEmptyString


class ChatResponse(BaseModel):
    conversation_id: NonEmptyString
    answer: NonEmptyString
