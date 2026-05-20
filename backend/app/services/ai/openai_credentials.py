"""OpenAI credential helpers.

Supports either classic API keys or OpenAI OAuth access tokens. Both are used as
Bearer tokens against OpenAI endpoints; OAuth tokens should be refreshed outside
this app before expiry unless a refresh flow is added later.
"""

from openai import AsyncOpenAI

from app.core.config import settings


def get_openai_bearer_token() -> str:
    """Return the configured OpenAI bearer token, preferring OAuth."""
    return settings.openai_oauth_access_token or settings.openai_api_key


def is_openai_configured() -> bool:
    """Return whether any OpenAI credential is configured."""
    return bool(get_openai_bearer_token())


def create_openai_client() -> AsyncOpenAI:
    """Create an OpenAI SDK client with the configured bearer token."""
    return AsyncOpenAI(api_key=get_openai_bearer_token())
