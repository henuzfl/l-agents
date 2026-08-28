from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "enterprise-agent"
    app_env: str = "development"
    log_level: str = "INFO"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    database_url: SecretStr | None = None
    short_term_memory_enabled: bool = True
    short_term_context_max_tokens: int = 12000
    short_term_summary_target_tokens: int = 1500
    short_term_recent_turns: int = 6
    short_term_min_recent_turns: int = 2
    short_term_summary_batch_turns: int = 4
    short_term_single_message_max_tokens: int = 4000
    short_term_fallback_turns: int = 10
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
    jwt_secret_key: SecretStr | None = None
    jwt_issuer: str = "enterprise-agent"
    jwt_audience: str = "enterprise-agent-web"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    refresh_cookie_secure: bool = False
    seed_demo_users: bool = False
    demo1_password: SecretStr | None = None
    demo2_password: SecretStr | None = None
    demo3_password: SecretStr | None = None
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: SecretStr | None = None
    minio_bucket: str = "knowledge-documents"
    minio_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_short_term_memory(self) -> "Settings":
        values = (
            self.short_term_context_max_tokens,
            self.short_term_summary_target_tokens,
            self.short_term_recent_turns,
            self.short_term_min_recent_turns,
            self.short_term_summary_batch_turns,
            self.short_term_single_message_max_tokens,
            self.short_term_fallback_turns,
        )
        if any(value <= 0 for value in values):
            raise ValueError("Short-term memory settings must be positive.")
        if self.short_term_min_recent_turns > self.short_term_recent_turns:
            raise ValueError("SHORT_TERM_MIN_RECENT_TURNS cannot exceed SHORT_TERM_RECENT_TURNS.")
        if self.short_term_summary_target_tokens >= self.short_term_context_max_tokens:
            raise ValueError("The short-term summary must be smaller than the context budget.")
        if self.short_term_single_message_max_tokens >= self.short_term_context_max_tokens:
            raise ValueError("A single message must be smaller than the context budget.")
        if self.access_token_minutes <= 0 or self.refresh_token_days <= 0:
            raise ValueError("JWT token lifetimes must be positive.")
        if self.seed_demo_users and any(
            password is None
            for password in (self.demo1_password, self.demo2_password, self.demo3_password)
        ):
            raise ValueError("SEED_DEMO_USERS requires DEMO1_PASSWORD through DEMO3_PASSWORD.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
