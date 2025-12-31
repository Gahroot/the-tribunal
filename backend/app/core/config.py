"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://aicrm:aicrm_dev_password@localhost:5432/aicrm"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # OpenAI
    openai_api_key: str = ""
    openai_timeout: int = 60

    # Telnyx
    telnyx_api_key: str = ""
    telnyx_webhook_secret: str = ""

    # Cal.com
    calcom_api_key: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # Workers
    campaign_poll_interval: int = 5
    ai_response_delay_ms: int = 2000


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
