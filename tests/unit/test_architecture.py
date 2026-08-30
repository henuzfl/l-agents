from app.auth import AuthService as PublicAuthService
from app.auth.service import AuthService
from app.chat import ChatService as PublicChatService
from app.chat.service import ChatService
from app.db import Base
from app.db_models import Base as CompatibilityBase


def test_compatibility_exports_reference_canonical_types() -> None:
    assert PublicAuthService is AuthService
    assert PublicChatService is ChatService
    assert CompatibilityBase is Base


def test_database_metadata_keeps_existing_table_names() -> None:
    assert set(Base.metadata.tables) == {
        "agent_messages",
        "agent_sessions",
        "knowledge_documents",
        "memory_summaries",
        "refresh_tokens",
        "users",
    }
