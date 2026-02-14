"""
Aegis Production Configuration

All settings with sensible defaults and environment variable overrides.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Database ----------
    database_url: str = Field(
        default="postgresql://aegis:aegis@localhost:5432/aegis",
        alias="DATABASE_URL",
    )

    # Optional read replica for scaling queries
    database_read_replica_url: str | None = Field(
        default=None,
        alias="DATABASE_READ_REPLICA_URL",
    )

    # Connection pool settings
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")

    sql_echo: bool = Field(default=False, alias="SQL_ECHO")

    # ---------- API ----------
    aegis_api_key: str = Field(
        default="dev-secret-key",
        alias="AEGIS_API_KEY",
    )
    default_project_id: str = Field(
        default="default-project",
        alias="AEGIS_DEFAULT_PROJECT_ID",
    )

    # ---------- OpenAI ----------
    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
    )
    openai_embed_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBED_MODEL",
    )
    embedding_dimensions: int = Field(
        default=1536,
        alias="EMBEDDING_DIMENSIONS",
    )
    openai_chat_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_CHAT_MODEL",
    )

    # ---------- Retrieval ----------
    default_top_k: int = Field(default=10, alias="DEFAULT_TOP_K")

    # ---------- Rate Limiting ----------
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, alias="RATE_LIMIT_PER_HOUR")
    rate_limit_burst: int = Field(default=10, alias="RATE_LIMIT_BURST")

    # ---------- Redis (optional, for distributed rate limiting) ----------
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # ---------- Auth ----------
    enable_project_auth: bool = Field(
        default=False,
        alias="ENABLE_PROJECT_AUTH",
        description="Enable project-scoped API key auth. When false, uses legacy single AEGIS_API_KEY.",
    )
    aegis_env: str = Field(
        default="development",
        alias="AEGIS_ENV",
        description="Environment: 'development' or 'production'. Controls schema init behavior.",
    )

    # ---------- CORS ----------
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # ---------- Observability Exporters ----------
    obs_langfuse_enabled: bool = Field(default=False, alias="OBS_LANGFUSE_ENABLED")
    obs_langsmith_enabled: bool = Field(default=False, alias="OBS_LANGSMITH_ENABLED")

    obs_langfuse_api_key: str | None = Field(default=None, alias="OBS_LANGFUSE_API_KEY")
    obs_langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="OBS_LANGFUSE_HOST")

    obs_langsmith_api_key: str | None = Field(default=None, alias="OBS_LANGSMITH_API_KEY")
    obs_langsmith_host: str = Field(default="https://api.smith.langchain.com", alias="OBS_LANGSMITH_HOST")

    obs_queue_max_size: int = Field(default=5000, alias="OBS_QUEUE_MAX_SIZE")
    obs_batch_size: int = Field(default=100, alias="OBS_BATCH_SIZE")
    obs_batch_flush_interval_ms: int = Field(default=500, alias="OBS_BATCH_FLUSH_INTERVAL_MS")
    obs_retry_max_attempts: int = Field(default=3, alias="OBS_RETRY_MAX_ATTEMPTS")
    obs_retry_base_delay_seconds: int = Field(default=2, alias="OBS_RETRY_BASE_DELAY_SECONDS")
    obs_export_timeout_seconds: int = Field(default=10, alias="OBS_EXPORT_TIMEOUT_SECONDS")

    def get_cors_origins(self) -> list[str]:
        raw_origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

        if raw_origins == ["*"]:
            return ["*"]

        if "*" in raw_origins:
            raise ValueError(
                "CORS_ORIGINS cannot mix '*' with explicit origins. "
                "Use '*' alone for non-credential mode."
            )

        return raw_origins

    def cors_allow_credentials(self) -> bool:
        return self.get_cors_origins() != ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
