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

    # ---------- CORS ----------
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    def get_cors_origins(self) -> list:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
