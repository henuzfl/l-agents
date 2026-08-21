from typing import Any, Protocol

from agents import Agent
from agents.memory import Session

from app.core.exceptions import AgentExecutionError, SessionError
from app.memory import SessionFactory
from app.schemas import ChatRequest, ChatResponse


class RunResultLike(Protocol):
    final_output: Any


class RunnerLike(Protocol):
    async def run(
        self,
        starting_agent: Agent[None],
        input: str,
        *,
        session: Session,
    ) -> RunResultLike: ...


class ChatService:
    def __init__(
        self,
        manager_agent: Agent[None],
        session_factory: SessionFactory,
        runner: RunnerLike,
    ) -> None:
        self._manager_agent = manager_agent
        self._session_factory = session_factory
        self._runner = runner

    async def chat(self, request: ChatRequest) -> ChatResponse:
        try:
            session = self._session_factory.create(request.user_id, request.conversation_id)
            result = await self._runner.run(
                self._manager_agent,
                request.message,
                session=session,
            )
        except SessionError:
            raise
        except Exception as exc:
            raise AgentExecutionError("The manager agent could not complete the request.") from exc

        answer = str(result.final_output or "").strip()
        if not answer:
            raise AgentExecutionError("The manager agent returned an empty response.")
        return ChatResponse(conversation_id=request.conversation_id, answer=answer)
