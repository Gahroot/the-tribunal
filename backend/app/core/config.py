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
    telnyx_public_key: str = ""
    skip_webhook_verification: bool = False
    # Telnyx Voice
    telnyx_connection_id: str = ""  # Required for outbound calls
    telnyx_app_id: str = ""  # TeXML application ID (optional)

    # Cal.com
    calcom_api_key: str = ""
    calcom_webhook_secret: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""

    # xAI (Grok)
    xai_api_key: str = ""

    # SendGrid
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@example.com"

    # Google Places API
    google_places_api_key: str = ""

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    api_base_url: str = ""  # Base URL for webhooks (e.g., https://api.example.com)
    frontend_url: str = "http://localhost:3000"  # Frontend URL for links in emails

    # Workers
    campaign_poll_interval: int = 5
    ai_response_delay_ms: int = 2000

    # Enrichment
    enable_ai_enrichment: bool = True  # Toggle AI website summary


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
