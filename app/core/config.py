from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "enterprise-agent"
    app_env: str = "development"
    log_level: str = "INFO"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    sqlite_session_path: Path = Path("data/sessions.db")
    knowledge_database_url: SecretStr | None = None
    knowledge_schema: str = "agent_knowledge"
    knowledge_table: str = "project_manual"
    dashscope_api_key: SecretStr | None = None
    qwen_embedding_base_url: str | None = None
    qwen_embedding_model: str = "text-embedding-v4"
    qwen_embedding_dimensions: int = 1024
    qwen_vision_base_url: str | None = None
    qwen_vision_model: str = "qwen3-vl-plus"
    qwen_vision_max_pages: int = 100
    qwen_vision_max_images: int = 50
    knowledge_top_k: int = 5
    knowledge_upload_max_bytes: int = 10 * 1024 * 1024
    knowledge_registry_path: Path = Path("data/knowledge_documents.db")
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: SecretStr | None = None
    minio_bucket: str = "knowledge-documents"
    minio_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
