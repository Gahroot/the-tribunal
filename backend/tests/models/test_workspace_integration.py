"""In-memory unit tests for ``WorkspaceIntegration`` credential handling.

These construct model instances without a database. They cover the encrypted
credentials round-trip and the resilient ``safe_credentials`` accessor that read
paths use so an undecryptable blob (corruption or a rotated encryption key)
surfaces as "present but unreadable" instead of raising and 500-ing the
settings/integrations page.
"""

from __future__ import annotations

import uuid

from app.core.encryption import encrypt_json
from app.models.workspace import WorkspaceIntegration


def _integration(encrypted_credentials: str) -> WorkspaceIntegration:
    return WorkspaceIntegration(
        workspace_id=uuid.uuid4(),
        integration_type="openai",
        encrypted_credentials=encrypted_credentials,
        is_active=True,
    )


def test_credentials_round_trip() -> None:
    integration = _integration(encrypt_json({"api_key": "sk-test", "email": "a@b.com"}))

    assert integration.credentials == {"api_key": "sk-test", "email": "a@b.com"}
    assert integration.safe_credentials() == {"api_key": "sk-test", "email": "a@b.com"}


def test_safe_credentials_returns_none_on_undecryptable_blob() -> None:
    # Fernet-looking token that won't decrypt under the configured key.
    integration = _integration("gAAAAABcorrupted-not-a-valid-fernet-token")

    assert integration.safe_credentials() is None


def test_raw_credentials_property_still_raises_on_undecryptable_blob() -> None:
    # safe_credentials must not change the strict behavior write paths rely on.
    integration = _integration("gAAAAABcorrupted-not-a-valid-fernet-token")

    raised = False
    try:
        _ = integration.credentials
    except Exception:  # noqa: BLE001 - asserting it raises at all is the point
        raised = True

    assert raised is True
