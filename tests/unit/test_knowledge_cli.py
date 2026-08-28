import pytest

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError
from app.knowledge.cli import run_command
from app.knowledge.store import KnowledgeStatus


class FakeStore:
    def __init__(self, _settings: Settings) -> None:
        self.initialized = False

    def initialize(self) -> None:
        self.initialized = True

    def rebuild(self) -> int:
        return 6

    def status(self) -> KnowledgeStatus:
        return KnowledgeStatus("agent_knowledge", "project_manual", 6, "text-embedding-v4", 1024)


def test_cli_commands_return_actionable_messages() -> None:
    settings = Settings()
    assert "初始化完成" in run_command("init", settings, FakeStore)  # type: ignore[arg-type]
    assert "6 个节点" in run_command("rebuild", settings, FakeStore)  # type: ignore[arg-type]
    assert "agent_knowledge.project_manual" in run_command(
        "status", settings, FakeStore  # type: ignore[arg-type]
    )


def test_default_store_reports_missing_configuration() -> None:
    settings = Settings(
        database_url=None,
        dashscope_api_key=None,
        qwen_embedding_base_url=None,
        _env_file=None,
    )
    with pytest.raises(KnowledgeConfigurationError):
        run_command("init", settings)
