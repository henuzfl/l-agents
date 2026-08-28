from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError
from app.knowledge.store import LlamaIndexKnowledgeStore


def base_settings(_tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql://user:password@example.com/database",
        "dashscope_api_key": "test-key",
        "qwen_embedding_base_url": "https://workspace.example.com/compatible-mode/v1",
        "qwen_embedding_dimensions": 1024,
    }
    values.update(overrides)
    return Settings(**values)


def test_qwen_embedding_configuration_uses_1024_dimensions(tmp_path: Path) -> None:
    embedding = LlamaIndexKnowledgeStore(base_settings(tmp_path)).create_embedding_model()
    assert embedding.model_name == "text-embedding-v4"
    assert embedding.dimensions == 1024


def test_store_requires_all_external_configuration(tmp_path: Path) -> None:
    settings = Settings(
        database_url=None,
        dashscope_api_key=None,
        qwen_embedding_base_url=None,
        _env_file=None,
    )
    store = LlamaIndexKnowledgeStore(settings)
    with pytest.raises(KnowledgeConfigurationError, match="DATABASE_URL"):
        store.create_vector_store()


def test_store_rejects_embedding_dimension_change(tmp_path: Path) -> None:
    store = LlamaIndexKnowledgeStore(
        base_settings(tmp_path, qwen_embedding_dimensions=768)
    )
    with pytest.raises(KnowledgeConfigurationError, match="1024"):
        store.create_embedding_model()


def test_vector_store_is_configured_for_pgvector_without_connecting(tmp_path: Path) -> None:
    vector_store = LlamaIndexKnowledgeStore(base_settings(tmp_path)).create_vector_store()
    assert vector_store.schema_name == "agent_knowledge"
    assert vector_store.table_name == "project_manual"
    assert vector_store.embed_dim == 1024
    assert vector_store.perform_setup is True
