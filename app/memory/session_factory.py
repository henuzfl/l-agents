from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from agents.memory import Session
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.exceptions import SessionError


class SessionFactory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def create(self, user_id: str, conversation_id: str) -> Session:
        session_id = f"{user_id}:{conversation_id}"
        try:
            return SQLAlchemySession(session_id, engine=self._engine, create_tables=False)
        except (TypeError, ValueError) as exc:
            raise SessionError("Unable to create the conversation session.") from exc
