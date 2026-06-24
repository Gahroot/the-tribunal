"""Service configuration.

Boots with safe defaults so the service runs locally with no ``.env``. Every
field below is documented in ``docs/blocks/SERVICE_BLOCK_PATTERN.md`` §3.

Production overrides are listed in ``.env.example`` and ``README.md``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the ``__BLOCK_ID__`` service, loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Service identity ----------------------------------------------------
    block_id: str = "__BLOCK_ID__"
    environment: str = "local"  # local | staging | production
    debug: bool = False

    # --- HTTP ----------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Host <-> service auth (HS256 JWT) -----------------------------------
    # Mirrors backend/app/core/security.py: symmetric HS256, type-discriminated.
    # Set SERVICE_TOKEN_SECRET to the host's SECRET_KEY (or a shared mesh secret)
    # in production. The default is a dev-only value so the service boots locally.
    service_token_secret: str = Field(
        default="dev-service-token-secret-not-for-production-use-32",
        min_length=32,
    )
    algorithm: str = "HS256"
    service_token_ttl_seconds: int = 300  # service tokens are short-lived

    # --- Host CRM callback target -------------------------------------------
    # The service calls the host's v1 API here (data it does not own) and POSTs
    # signed events to HOST_API_URL + host_event_webhook_path.
    host_api_url: str = "http://localhost:8000"
    host_event_webhook_path: str = "/webhooks/service/__BLOCK_ID__"

    # --- Fernet vault (only when the service owns a slice — §3.3(b)) ---------
    # When the service decrypts per-workspace credentials itself, set this to the
    # same ENCRYPTION_KEY as the host so Fernet ciphertext round-trips unchanged.
    encryption_key: str = "change-me-in-production"

    # --- Optional infra for the readiness probe ------------------------------
    # When empty, /readyz skips that check (stateless services + local dev).
    database_url: str = ""
    redis_url: str = ""

    # --- External provider webhooks ------------------------------------------
    # Dev-only bypass that mirrors backend/app/core/webhook_security.py.
    skip_webhook_verification: bool = False

    # --- Worker ---------------------------------------------------------------
    run_worker: bool = True
    worker_poll_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()


settings = get_settings()
