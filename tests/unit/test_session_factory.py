from pathlib import Path

from agents import SQLiteSession

from app.memory import SessionFactory


def test_session_factory_builds_expected_session_id(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    session = SessionFactory(database).create("user-001", "conversation-001")
    assert isinstance(session, SQLiteSession)
    assert session.session_id == "user-001:conversation-001"
