"""Validation and auth tests for the campaigns API endpoints.

Focuses on Pydantic validation failures, auth failures, and common
error-path branches (e.g. state-machine transitions). DB is fully mocked.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import campaigns as campaigns_module

WS_ID = uuid.uuid4()
CAMPAIGN_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Minimal lifespan that skips workers, Redis, and DB setup."""
    yield


def _make_mock_workspace() -> MagicMock:
    """Build a mock Workspace."""
    ws = MagicMock()
    ws.id = WS_ID
    ws.is_active = True
    ws.settings = {}
    return ws


def _make_mock_user() -> MagicMock:
    """Build a mock User."""
    user = MagicMock()
    user.id = 1
    user.is_active = True
    user.email = "tester@example.com"
    return user


def _make_mock_campaign(
    status: str = "draft",
    campaign_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock Campaign with reasonable defaults."""
    from datetime import UTC, datetime

    c = MagicMock()
    c.id = campaign_id or CAMPAIGN_ID
    c.workspace_id = WS_ID
    c.campaign_type = "sms"
    c.agent_id = None
    c.offer_id = None
    c.name = "Test Campaign"
    c.status = status
    c.from_phone_number = "+15551234567"
    c.initial_message = "Hello"
    c.ai_enabled = True
    c.qualification_criteria = None
    c.scheduled_start = None
    c.sending_hours_start = None
    c.sending_hours_end = None
    c.sending_days = None
    c.timezone = "America/New_York"
    c.messages_per_minute = 10
    c.follow_up_enabled = False
    c.follow_up_delay_hours = 24
    c.follow_up_message = None
    c.max_follow_ups = 2
    c.total_contacts = 0
    c.messages_sent = 0
    c.messages_delivered = 0
    c.messages_failed = 0
    c.replies_received = 0
    c.contacts_qualified = 0
    c.contacts_opted_out = 0
    c.appointments_booked = 0
    c.appointments_completed = 0
    c.guarantee_target = None
    c.guarantee_window_days = None
    c.guarantee_status = None
    c.started_at = None
    c.created_at = datetime.now(UTC)
    c.updated_at = datetime.now(UTC)
    return c


def _make_auth_test_app(
    mock_db: AsyncMock, mock_workspace: MagicMock, mock_user: MagicMock
) -> FastAPI:
    """Create a test app with auth/workspace/db dependencies overridden."""
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_get_workspace() -> MagicMock:
        return mock_workspace

    async def override_get_current_user() -> MagicMock:
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_current_user] = override_get_current_user

    app.include_router(
        campaigns_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/campaigns",
    )
    from app.api.v1 import voice_campaigns

    app.include_router(
        voice_campaigns.router,
        prefix="/api/v1/workspaces/{workspace_id}/voice-campaigns",
    )
    return app


def _make_noauth_test_app() -> FastAPI:
    """Create a test app without dependency overrides (auth fails)."""
    app = FastAPI(lifespan=_test_lifespan)
    app.include_router(
        campaigns_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/campaigns",
    )
    return app


@pytest.fixture
def mock_db() -> AsyncMock:
    """Async DB session mock."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def mock_workspace() -> MagicMock:
    """Mock Workspace."""
    return _make_mock_workspace()


@pytest.fixture
def mock_user() -> MagicMock:
    """Mock User."""
    return _make_mock_user()


@pytest.fixture
async def client(
    mock_db: AsyncMock, mock_workspace: MagicMock, mock_user: MagicMock
) -> AsyncIterator[AsyncClient]:
    """Authenticated client (dependency overrides active)."""
    app = _make_auth_test_app(mock_db, mock_workspace, mock_user)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
async def noauth_client() -> AsyncIterator[AsyncClient]:
    """Unauthenticated client (no overrides)."""
    app = _make_noauth_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestListCampaigns:
    """GET /campaigns validation + auth."""

    async def test_list_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """GET /campaigns without auth returns 401."""
        response = await noauth_client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns"
        )
        assert response.status_code == 401

    async def test_list_invalid_page_returns_422(
        self, client: AsyncClient
    ) -> None:
        """GET /campaigns with page=0 returns 422."""
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns?page=0"
        )
        assert response.status_code == 422

    async def test_list_page_size_over_limit_returns_422(
        self, client: AsyncClient
    ) -> None:
        """GET /campaigns with page_size=200 (violates le=100) returns 422."""
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns?page_size=200"
        )
        assert response.status_code == 422


class TestCreateCampaignValidation:
    """POST /campaigns validation."""

    async def test_create_missing_name_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns without name returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={
                "from_phone_number": "+15551234567",
                "initial_message": "Hi",
            },
        )
        assert response.status_code == 422

    async def test_create_missing_phone_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns without from_phone_number returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={"name": "Test", "initial_message": "Hi"},
        )
        assert response.status_code == 422

    async def test_create_missing_initial_message_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns without initial_message returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={"name": "Test", "from_phone_number": "+15551234567"},
        )
        assert response.status_code == 422

    async def test_create_invalid_agent_uuid_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns with malformed agent_id returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={
                "name": "Test",
                "from_phone_number": "+15551234567",
                "initial_message": "Hi",
                "agent_id": "not-a-uuid",
            },
        )
        assert response.status_code == 422

    async def test_create_empty_body_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns with empty body returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={},
        )
        assert response.status_code == 422

    async def test_create_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={
                "name": "Test",
                "from_phone_number": "+15551234567",
                "initial_message": "Hi",
            },
        )
        assert response.status_code == 401

    async def test_create_with_nonexistent_agent_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """POST /campaigns with a valid-UUID but unknown agent_id returns 404."""
        agent_uuid = uuid.uuid4()

        # db.execute returns a result whose scalar_one_or_none() is None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns",
            json={
                "name": "Test",
                "from_phone_number": "+15551234567",
                "initial_message": "Hi",
                "agent_id": str(agent_uuid),
            },
        )
        assert response.status_code == 404


class TestGetCampaign:
    """GET /campaigns/{id}."""

    async def test_get_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """GET /campaigns/{id} without auth returns 401."""
        response = await noauth_client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}"
        )
        assert response.status_code == 401

    async def test_get_invalid_uuid_returns_422(
        self, client: AsyncClient
    ) -> None:
        """GET /campaigns/{id} with non-UUID returns 422."""
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns/not-a-uuid"
        )
        assert response.status_code == 422

    async def test_get_nonexistent_returns_404(
        self, client: AsyncClient
    ) -> None:
        """GET /campaigns/{id} with unknown id returns 404."""
        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(
                side_effect=__import__(
                    "fastapi"
                ).HTTPException(status_code=404, detail="Not found")
            ),
        ):
            response = await client.get(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{uuid.uuid4()}"
            )
        assert response.status_code == 404


class TestUpdateCampaign:
    """PUT /campaigns/{id}."""

    async def test_update_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """PUT /campaigns/{id} without auth returns 401."""
        response = await noauth_client.put(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}",
            json={"name": "Updated"},
        )
        assert response.status_code == 401

    async def test_update_running_campaign_returns_400(
        self, client: AsyncClient
    ) -> None:
        """PUT /campaigns/{id} on a running campaign returns 400."""
        running_campaign = _make_mock_campaign(status="running")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=running_campaign),
        ):
            response = await client.put(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}",
                json={"name": "Updated"},
            )

        assert response.status_code == 400


class TestStartCampaign:
    """POST /campaigns/{id}/start state transitions."""

    async def test_start_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/start without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/start"
        )
        assert response.status_code == 401

    async def test_start_wrong_status_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/start when already running returns 400."""
        running = _make_mock_campaign(status="running")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=running),
        ), patch("app.api.v1.campaigns._validate_campaign_sender", new=AsyncMock()):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/start"
            )

        assert response.status_code == 400

    async def test_start_with_no_contacts_returns_400(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """POST /campaigns/{id}/start with zero contacts returns 400."""
        draft = _make_mock_campaign(status="draft")

        # Contact count query returns 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=count_result)

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=draft),
        ), patch("app.api.v1.campaigns._validate_campaign_sender", new=AsyncMock()):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/start"
            )

        assert response.status_code == 400
        assert "no contacts" in response.json()["detail"].lower()

    async def test_start_with_no_eligible_recipients_returns_409_with_recovery(
        self, client: AsyncClient
    ) -> None:
        """Zero eligible SMS recipients → 409 carrying counts and reasons."""
        from datetime import UTC, datetime

        from app.services.campaigns.campaign_lifecycle import CampaignNotSendableError
        from app.services.campaigns.recipient_eligibility import (
            RecipientEligibility,
            RecipientExclusion,
        )

        eligibility = RecipientEligibility(
            channel="sms",
            consent_required=True,
            checked_at=datetime.now(UTC),
            selected_count=2,
            exclusions=[
                RecipientExclusion(reason="missing_sms_consent", count=2, contact_ids=[1, 2])
            ],
        )
        draft = _make_mock_campaign(status="draft")
        with (
            patch("app.api.v1.campaigns.get_or_404", new=AsyncMock(return_value=draft)),
            patch("app.api.v1.campaigns._validate_campaign_sender", new=AsyncMock()),
            patch(
                "app.api.v1.campaigns.start_campaign_lifecycle",
                new=AsyncMock(side_effect=CampaignNotSendableError("nobody", eligibility)),
            ),
        ):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/start"
            )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "no_eligible_recipients"
        assert detail["details"]["eligible_count"] == 0
        assert detail["details"]["ready_to_send"] is False
        exclusion = detail["details"]["exclusions"][0]
        assert exclusion["reason"] == "missing_sms_consent"
        assert exclusion["recoverable_with_consent"] is True
        assert exclusion["contact_ids"] == [1, 2]


class TestSharedCampaignReadiness:
    """RF-011: exercise real start/resume and lifecycle, never a sending worker."""

    @pytest.mark.parametrize("action", ["start", "resume"])
    @pytest.mark.parametrize("route", ["campaigns", "voice-campaigns"])
    @pytest.mark.parametrize(
        "case, expected, message",
        [
            ("voice_only", 200, None),
            ("non_voice", 400, "voice-enabled"),
            ("inactive", 400, "voice-enabled"),
            ("foreign_sender", 400, "this workspace"),
            ("wrong_provider", 400, "Telnyx number"),
            ("missing_agent", 400, "Select a voice agent"),
            ("text_agent", 400, "active voice agent"),
            ("foreign_agent", 400, "this workspace"),
            ("inactive_agent", 400, "active voice agent"),
            ("no_telnyx", 503, "TELNYX_API_KEY"),
            ("no_openai", 503, "OPENAI_API_KEY"),
            ("no_grok", 503, "XAI_API_KEY"),
            ("no_elevenlabs", 503, "ELEVENLABS_API_KEY and XAI_API_KEY"),
        ],
    )
    async def test_voice_readiness(self, client, mock_db, action, route, case, expected, message):
        from app.models.agent import Agent
        from app.models.campaign import Campaign, CampaignContact, CampaignType
        from app.models.phone_number import PhoneNumber, PhoneNumberProvider
        from app.services.campaigns.campaign_lifecycle import settings

        campaign = _make_mock_campaign(status="paused" if action == "resume" else "draft")
        campaign.campaign_type = CampaignType.VOICE_SMS_FALLBACK
        campaign.voice_agent_id = None if case == "missing_agent" else uuid.uuid4()
        campaign.voice_experiment = None
        sender = PhoneNumber(
            workspace_id=uuid.uuid4() if case == "foreign_sender" else WS_ID,
            phone_number=campaign.from_phone_number,
            provider=PhoneNumberProvider.MAC_RELAY
            if case == "wrong_provider"
            else PhoneNumberProvider.TELNYX,
            is_active=case != "inactive",
            voice_enabled=case != "non_voice",
            sms_enabled=False,
            imessage_enabled=False,
        )
        agent = Agent(
            id=campaign.voice_agent_id,
            workspace_id=uuid.uuid4() if case == "foreign_agent" else WS_ID,
            is_active=case != "inactive_agent",
            channel_mode="text" if case == "text_agent" else "voice",
            voice_provider={"no_grok": "grok", "no_elevenlabs": "elevenlabs"}.get(case, "openai"),
        )

        async def execute(query):
            # Honor the actual WHERE predicates; a missing tenant/channel filter fails tests.
            from sqlalchemy.sql import operators
            from sqlalchemy.sql.elements import BindParameter
            from sqlalchemy.sql.visitors import iterate

            model = query.column_descriptions[0]["entity"]
            result = MagicMock()
            if model is CampaignContact:
                result.scalar.return_value = 1
                return result
            row = {Campaign: campaign, PhoneNumber: sender, Agent: agent}[model]
            matches = True
            for clause in iterate(query.whereclause):
                if getattr(clause, "operator", None) not in (operators.eq, operators.is_):
                    continue
                value = (
                    clause.right.value
                    if isinstance(clause.right, BindParameter)
                    else str(clause.right) == "true"
                )
                matches = matches and getattr(row, clause.left.key) == value
            result.scalar_one_or_none.return_value = row if matches else None
            return result

        mock_db.execute.side_effect = execute
        initial_status = campaign.status
        with (
            patch.object(settings, "telnyx_api_key", "" if case == "no_telnyx" else "test-key"),
            patch.object(settings, "openai_api_key", "" if case == "no_openai" else "test-key"),
            patch.object(settings, "openai_oauth_access_token", ""),
            patch.object(settings, "xai_api_key", ""),
            patch.object(settings, "elevenlabs_api_key", ""),
        ):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/{route}/{CAMPAIGN_ID}/{action}"
            )
        assert response.status_code == expected, response.text
        if expected == 200:
            assert response.json()["status"] == "running"
            if route == "campaigns":
                assert response.json()["eligibility"] is None
            assert campaign.status == "running"
            mock_db.commit.assert_awaited_once()
        else:
            assert message in response.json()["detail"]
            assert campaign.status == initial_status
            mock_db.commit.assert_not_awaited()

    @pytest.mark.parametrize("action", ["start", "resume"])
    @pytest.mark.parametrize(
        "sms, imessage, telnyx, relay, expected, message",
        [
            (False, False, True, True, 400, "SMS or iMessage"),
            (True, False, False, True, 400, "Telnyx SMS"),
            (False, True, True, False, 400, "iMessage relay"),
            (True, False, True, False, 200, None),
            (False, True, False, True, 200, None),
        ],
    )
    async def test_text_checks_unchanged(
        self, client, mock_db, action, sms, imessage, telnyx, relay, expected, message
    ):
        from datetime import UTC, datetime

        from app.services.campaigns.recipient_eligibility import RecipientEligibility

        campaign = _make_mock_campaign(status="paused" if action == "resume" else "draft")
        sender_result = MagicMock()
        sender_result.scalar_one_or_none.return_value = MagicMock(
            sms_enabled=sms, imessage_enabled=imessage
        )
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        integration_result = MagicMock()
        integration_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = (
            [sender_result, integration_result, count_result]
            if sms and not imessage else [sender_result, count_result]
        )
        eligibility = RecipientEligibility(
            channel="sms" if sms else "imessage",
            consent_required=sms,
            checked_at=datetime.now(UTC),
            selected_count=1,
            eligible_count=1,
        )
        with (
            patch("app.api.v1.campaigns.get_or_404", new=AsyncMock(return_value=campaign)),
            patch.object(campaigns_module.settings, "telnyx_api_key", "test" if telnyx else ""),
            patch.object(
                campaigns_module.settings, "mac_relay_base_url", "http://stub" if relay else ""
            ),
            patch.object(campaigns_module.settings, "mac_relay_token", "test" if relay else ""),
            patch(
                "app.services.campaigns.campaign_lifecycle.RecipientEligibilityService"
            ) as service,
        ):
            service.return_value.evaluate_campaign = AsyncMock(return_value=eligibility)
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/{action}"
            )
        assert response.status_code == expected, response.text
        if expected == 400:
            assert message in response.json()["detail"]
            service.return_value.evaluate_campaign.assert_not_awaited()
            mock_db.commit.assert_not_awaited()
        else:
            assert response.json()["eligibility"]["eligible_count"] == 1
            service.return_value.evaluate_campaign.assert_awaited_once_with(mock_db, campaign)
            mock_db.commit.assert_awaited_once()


class TestPauseCampaign:
    """POST /campaigns/{id}/pause."""

    async def test_pause_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/pause without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/pause"
        )
        assert response.status_code == 401

    async def test_pause_non_running_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/pause on a draft campaign returns 400."""
        draft = _make_mock_campaign(status="draft")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=draft),
        ):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/pause"
            )

        assert response.status_code == 400


class TestResumeCampaign:
    """POST /campaigns/{id}/resume."""

    async def test_resume_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/resume without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/resume"
        )
        assert response.status_code == 401

    async def test_resume_non_paused_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/resume on a draft campaign returns 400."""
        draft = _make_mock_campaign(status="draft")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=draft),
        ), patch("app.api.v1.campaigns._validate_campaign_sender", new=AsyncMock()):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/resume"
            )

        assert response.status_code == 400


class TestCancelCampaign:
    """POST /campaigns/{id}/cancel."""

    async def test_cancel_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/cancel without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/cancel"
        )
        assert response.status_code == 401

    async def test_cancel_running_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/cancel on a running campaign returns 400."""
        running = _make_mock_campaign(status="running")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=running),
        ):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/cancel"
            )

        assert response.status_code == 400


class TestAddContactsValidation:
    """POST /campaigns/{id}/contacts."""

    async def test_add_contacts_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/contacts without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/contacts",
            json={"contact_ids": [1, 2]},
        )
        assert response.status_code == 401

    async def test_add_contacts_missing_body_returns_422(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/contacts without body returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/contacts",
            json={},
        )
        assert response.status_code == 422

    async def test_add_contacts_to_running_campaign_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST /campaigns/{id}/contacts on a running campaign returns 400."""
        running = _make_mock_campaign(status="running")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=running),
        ):
            response = await client.post(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/contacts",
                json={"contact_ids": [1, 2, 3]},
            )

        assert response.status_code == 400


class TestListCampaignContacts:
    """GET /campaigns/{id}/contacts."""

    async def test_list_contacts_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """GET /campaigns/{id}/contacts without auth returns 401."""
        response = await noauth_client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/contacts"
        )
        assert response.status_code == 401

    async def test_list_contacts_limit_too_large_returns_422(
        self, client: AsyncClient
    ) -> None:
        """GET /campaigns/{id}/contacts with limit=1000 (violates le=500) returns 422."""
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}/contacts?limit=1000"
        )
        assert response.status_code == 422


class TestDeleteCampaign:
    """DELETE /campaigns/{id}."""

    async def test_delete_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """DELETE /campaigns/{id} without auth returns 401."""
        response = await noauth_client.delete(
            f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}"
        )
        assert response.status_code == 401

    async def test_delete_running_returns_400(
        self, client: AsyncClient
    ) -> None:
        """DELETE /campaigns/{id} on a running campaign returns 400."""
        running = _make_mock_campaign(status="running")

        with patch(
            "app.api.v1.campaigns.get_or_404",
            new=AsyncMock(return_value=running),
        ):
            response = await client.delete(
                f"/api/v1/workspaces/{WS_ID}/campaigns/{CAMPAIGN_ID}"
            )

        assert response.status_code == 400
