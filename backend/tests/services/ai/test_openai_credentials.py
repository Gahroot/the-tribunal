"""Tests for OpenAI credential resolution."""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.core.encryption import encrypt_json
from app.models.workspace import WorkspaceIntegration
from app.services.ai.openai_credentials import OpenAICredentialError, resolve_openai_credentials


class _ScalarResult:
    def __init__(self, row: Any | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any | None:
        return self._row


class _AsyncDB:
    def __init__(self, integration: WorkspaceIntegration | None) -> None:
        self.integration = integration
        self.execute = AsyncMock(return_value=_ScalarResult(integration))
        self.commit = AsyncMock()


def _jwt_with_account(account_id: str) -> str:
    payload = {
        "https://api.openai.com/auth": {
            "chatgpt_account_id": account_id,
        }
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def _workspace_integration(credentials: dict[str, Any]) -> WorkspaceIntegration:
    integration = WorkspaceIntegration(
        workspace_id=uuid.uuid4(),
        integration_type="openai",
        encrypted_credentials=encrypt_json(credentials),
        is_active=True,
    )
    return integration


@pytest.fixture(autouse=True)
def _reset_openai_settings() -> None:
    settings.openai_api_key = ""
    settings.openai_oauth_access_token = ""
    settings.openai_oauth_refresh_token = ""
    settings.openai_oauth_expires_at = None
    settings.openai_oauth_account_id = ""
    settings.openai_oauth_client_id = ""
    settings.openai_oauth_originator = ""
    settings.openai_oauth_user_agent = ""


async def test_workspace_api_key_takes_precedence_over_env() -> None:
    settings.openai_api_key = "sk-env"
    integration = _workspace_integration({"api_key": "sk-workspace", "organization_id": "org_123"})
    db = _AsyncDB(integration)

    context = await resolve_openai_credentials(db, integration.workspace_id)

    assert context.bearer_token == "sk-workspace"
    assert context.source == "workspace_api_key"
    assert context.organization_id == "org_123"
    db.commit.assert_not_called()


async def test_expired_workspace_oauth_refreshes_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refreshed_token = _jwt_with_account("acct_refreshed")
    integration = _workspace_integration(
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
            "expires_at": int(time.time() * 1000) - 60_000,
            "organization_id": "org_workspace",
        }
    )
    db = _AsyncDB(integration)
    settings.openai_oauth_client_id = "client-id"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(settings.openai_oauth_token_url)
        assert b"grant_type=refresh_token" in request.content
        assert b"refresh_token=refresh-token" in request.content
        assert b"client_id=client-id" in request.content
        return httpx.Response(
            200,
            json={
                "access_token": refreshed_token,
                "refresh_token": "refresh-token-2",
                "expires_in": 3600,
            },
        )

    original_async_client = httpx.AsyncClient

    def mock_async_client(**_: Any) -> httpx.AsyncClient:
        return original_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    context = await resolve_openai_credentials(db, integration.workspace_id)

    assert context.bearer_token == refreshed_token
    assert context.source == "workspace_oauth"
    assert context.account_id == "acct_refreshed"
    assert context.organization_id == "org_workspace"
    assert context.is_oauth is True
    db.commit.assert_awaited_once()
    persisted = integration.credentials
    assert persisted["access_token"] == refreshed_token
    assert persisted["refresh_token"] == "refresh-token-2"
    assert persisted["account_id"] == "acct_refreshed"


async def test_env_fallback_when_workspace_integration_missing() -> None:
    settings.openai_api_key = "sk-env"
    db = _AsyncDB(None)

    context = await resolve_openai_credentials(db, uuid.uuid4())

    assert context.bearer_token == "sk-env"
    assert context.source == "env_api_key"


async def test_missing_credentials_raise_generic_error() -> None:
    with pytest.raises(OpenAICredentialError, match="OpenAI credentials are not configured"):
        await resolve_openai_credentials()


async def test_expired_oauth_refresh_failure_does_not_fall_back_to_env() -> None:
    settings.openai_api_key = "sk-env"
    integration = _workspace_integration(
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
            "expires_at": int(time.time() * 1000) - 60_000,
        }
    )
    db = _AsyncDB(integration)

    with pytest.raises(OpenAICredentialError, match="refreshed"):
        await resolve_openai_credentials(db, integration.workspace_id)


@pytest.mark.parametrize("use_workspace_key", [True, False])
async def test_sms_uses_resolved_credentials_for_opt_out_and_response(
    monkeypatch: pytest.MonkeyPatch,
    use_workspace_key: bool,
) -> None:
    from app.models.agent import Agent
    from app.models.conversation import Conversation, Message
    from app.services.ai import text_agent

    settings.openai_api_key = "test-global-key"
    integration = _workspace_integration({"api_key": "test-workspace-key"})
    workspace_id = integration.workspace_id
    conversation = Conversation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        assigned_agent_id=uuid.uuid4(),
        ai_enabled=True,
        ai_paused=False,
    )
    agent = Agent(id=conversation.assigned_agent_id, workspace_id=workspace_id, is_active=True)
    db = _AsyncDB(integration if use_workspace_key else None)
    db.execute.side_effect = [
        _ScalarResult(conversation),
        _ScalarResult(agent),
        _ScalarResult(db.integration),
        _ScalarResult(Message(body="please stop kidding")),
    ]
    classifier = AsyncMock(return_value=False)
    generator = AsyncMock(return_value="")
    sender = AsyncMock()
    monkeypatch.setattr(text_agent, "has_potential_opt_out_keywords", lambda _: True)
    monkeypatch.setattr(text_agent, "build_message_context", AsyncMock(return_value=[]))
    monkeypatch.setattr(text_agent, "classify_opt_out_intent", classifier)
    monkeypatch.setattr(text_agent, "_active_prompt_version_id", AsyncMock(return_value=None))
    monkeypatch.setattr(text_agent, "generate_text_response", generator)
    monkeypatch.setattr(text_agent, "_send_ai_text_response_after_delay", sender)

    await text_agent.process_inbound_with_ai(conversation.id, workspace_id, db)

    expected_key = "test-workspace-key" if use_workspace_key else "test-global-key"
    classifier.assert_awaited_once()
    generator.assert_awaited_once()
    assert classifier.await_args.kwargs["openai_api_key"] == expected_key
    assert generator.await_args.kwargs["openai_api_key"] == expected_key
    sender.assert_not_awaited()
    for call, table in zip(
        db.execute.await_args_list[:2], ["conversations", "agents"], strict=True
    ):
        query = call.args[0]
        assert f"{table}.workspace_id =" in str(query)
        assert query.compile().params["workspace_id_1"] == workspace_id


@pytest.mark.parametrize("expired_workspace_oauth", [False, True])
async def test_sms_stops_when_credentials_cannot_be_resolved(
    monkeypatch: pytest.MonkeyPatch,
    expired_workspace_oauth: bool,
) -> None:
    from app.models.agent import Agent
    from app.models.conversation import Conversation
    from app.services.ai import openai_credentials, text_agent

    workspace_id = uuid.uuid4()
    integration = None
    if expired_workspace_oauth:
        settings.openai_api_key = "test-global-key"
        integration = _workspace_integration(
            {
                "access_token": "test-expired-token",
                "refresh_token": "test-refresh-token",
                "expires_at": int(time.time() * 1000) - 60_000,
            }
        )
        workspace_id = integration.workspace_id
    conversation = Conversation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        assigned_agent_id=uuid.uuid4(),
        ai_enabled=True,
        ai_paused=False,
    )
    agent = Agent(id=conversation.assigned_agent_id, workspace_id=workspace_id, is_active=True)
    db = _AsyncDB(integration)
    db.execute.side_effect = [
        _ScalarResult(conversation),
        _ScalarResult(agent),
        _ScalarResult(integration),
    ]
    monkeypatch.setattr(
        openai_credentials,
        "refresh_openai_oauth_token",
        AsyncMock(side_effect=OpenAICredentialError("OpenAI credentials could not be refreshed")),
    )
    classifier = AsyncMock()
    generator = AsyncMock()
    sender = AsyncMock()
    monkeypatch.setattr(text_agent, "classify_opt_out_intent", classifier)
    monkeypatch.setattr(text_agent, "generate_text_response", generator)
    monkeypatch.setattr(text_agent, "_send_ai_text_response_after_delay", sender)

    await text_agent.process_inbound_with_ai(conversation.id, workspace_id, db)

    classifier.assert_not_awaited()
    generator.assert_not_awaited()
    sender.assert_not_awaited()
    db.commit.assert_not_awaited()
