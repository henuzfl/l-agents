from pathlib import Path

from agents import SQLiteSession
from agents.memory import Session

from app.core.exceptions import SessionError


class SessionFactory:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def create(self, user_id: str, conversation_id: str) -> Session:
        session_id = f"{user_id}:{conversation_id}"
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            return SQLiteSession(session_id, self._database_path)
        except (OSError, ValueError) as exc:
            raise SessionError("Unable to create the conversation session.") from exc
