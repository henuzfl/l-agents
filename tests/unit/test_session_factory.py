from pathlib import Path

from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from sqlalchemy.ext.asyncio import create_async_engine

from app.memory import SessionFactory


def test_session_factory_builds_expected_session_id(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    session = SessionFactory(engine).create("user-001", "conversation-001")
    assert isinstance(session, SQLAlchemySession)
    assert session.session_id == "user-001:conversation-001"
