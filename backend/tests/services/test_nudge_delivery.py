"""Tests for the NudgeDeliveryService.

Unit tests with mocked AsyncSession, httpx, and push notifications.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nudges.nudge_delivery import NudgeDeliveryService


@pytest.fixture
def delivery() -> NudgeDeliveryService:
    return NudgeDeliveryService()


def _make_nudge(
    workspace_id: uuid.UUID | None = None,
    assigned_to_user_id: int | None = None,
) -> MagicMock:
    nudge = MagicMock()
    nudge.id = uuid.uuid4()
    nudge.workspace_id = workspace_id or uuid.uuid4()
    nudge.contact_id = 1
    nudge.nudge_type = "birthday"
    nudge.title = "🎂 Alice's birthday"
    nudge.message = "Alice's birthday is in 2 days."
    nudge.status = "pending"
    nudge.assigned_to_user_id = assigned_to_user_id
    nudge.delivered_at = None
    nudge.delivered_via = None
    return nudge


def _make_workspace(nudge_settings: dict | None = None) -> MagicMock:
    ws = MagicMock()
    ws.id = uuid.uuid4()
    ws.settings = {
        "nudge_settings": nudge_settings or {
            "delivery_channels": ["sms", "push"],
        }
    }
    return ws


def _make_user(
    user_id: int = 1,
    phone_number: str | None = "+15551234567",
    notification_sms: bool = True,
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.phone_number = phone_number
    user.notification_sms = notification_sms
    user.is_active = is_active
    return user


def _scalar_result(value):
    result = MagicMock()
    result.scalars.return_value.all.return_value = value
    return result


def _scalar_one_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _unique_scalar_one_result(value):
    result = MagicMock()
    result.unique.return_value.scalar_one_or_none.return_value = value
    return result


def _make_membership(user: MagicMock) -> MagicMock:
    m = MagicMock()
    m.user = user
    return m


class TestDeliverToWorkspaceMembers:
    async def test_deliver_to_workspace_members(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """Nudge delivered via push + SMS → marked as sent."""
        ws = _make_workspace()
        nudge = _make_nudge(workspace_id=ws.id)
        user = _make_user()
        membership = _make_membership(user)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_result(ws),          # load workspace
                _scalar_result([membership]),     # resolve target users
                _scalar_one_result("+15550000000"),  # resolve from number
            ]
        )
        mock_db.commit = AsyncMock()

        with (
            patch(
                "app.services.nudges.nudge_delivery.push_notification_service"
            ) as mock_push,
            patch("app.services.nudges.nudge_delivery.httpx.AsyncClient") as mock_httpx_cls,
            patch("app.services.nudges.nudge_delivery.settings") as mock_settings,
        ):
            mock_settings.telnyx_api_key = "fake-key"
            mock_push.send_to_workspace_members = AsyncMock()

            mock_client = AsyncMock()
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock()

            result = await delivery.deliver_nudge(mock_db, nudge)

        assert result is True
        assert nudge.status == "sent"
        assert nudge.delivered_at is not None
        mock_db.commit.assert_awaited_once()


class TestSkipUsersWithoutPhone:
    async def test_skip_users_without_phone(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """User without phone_number → SMS not sent, push still works."""
        ws = _make_workspace()
        nudge = _make_nudge(workspace_id=ws.id)
        user_no_phone = _make_user(phone_number=None)
        membership = _make_membership(user_no_phone)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_result(ws),
                _scalar_result([membership]),
                _scalar_one_result("+15550000000"),
            ]
        )
        mock_db.commit = AsyncMock()

        with (
            patch(
                "app.services.nudges.nudge_delivery.push_notification_service"
            ) as mock_push,
            patch("app.services.nudges.nudge_delivery.httpx.AsyncClient") as mock_httpx_cls,
            patch("app.services.nudges.nudge_delivery.settings") as mock_settings,
        ):
            mock_settings.telnyx_api_key = "fake-key"
            mock_push.send_to_workspace_members = AsyncMock()

            mock_client = AsyncMock()
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await delivery.deliver_nudge(mock_db, nudge)

        assert result is True
        # SMS client.post should not have been called for a user without phone
        mock_client.post.assert_not_called()


class TestSkipUsersSmsDisabled:
    async def test_skip_users_sms_disabled(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """User with notification_sms=False → SMS not sent."""
        ws = _make_workspace()
        nudge = _make_nudge(workspace_id=ws.id)
        user = _make_user(notification_sms=False)
        membership = _make_membership(user)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_result(ws),
                _scalar_result([membership]),
                _scalar_one_result("+15550000000"),
            ]
        )
        mock_db.commit = AsyncMock()

        with (
            patch(
                "app.services.nudges.nudge_delivery.push_notification_service"
            ) as mock_push,
            patch("app.services.nudges.nudge_delivery.httpx.AsyncClient") as mock_httpx_cls,
            patch("app.services.nudges.nudge_delivery.settings") as mock_settings,
        ):
            mock_settings.telnyx_api_key = "fake-key"
            mock_push.send_to_workspace_members = AsyncMock()

            mock_client = AsyncMock()
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await delivery.deliver_nudge(mock_db, nudge)

        assert result is True
        mock_client.post.assert_not_called()


class TestQuietHoursRespected:
    def test_quiet_hours_during_quiet_period(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """23:00 UTC falls within default quiet hours (22:00-08:00)."""
        ws = _make_workspace()
        late_night = datetime(2026, 3, 28, 23, 0, 0, tzinfo=UTC)

        with patch(
            "app.services.nudges.nudge_delivery.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = late_night
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = delivery._is_quiet_hours(ws)

        assert result is True

    def test_not_quiet_hours_during_day(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """14:00 UTC is outside quiet hours."""
        ws = _make_workspace()
        afternoon = datetime(2026, 3, 28, 14, 0, 0, tzinfo=UTC)

        with patch(
            "app.services.nudges.nudge_delivery.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = afternoon
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = delivery._is_quiet_hours(ws)

        assert result is False


class TestNudgeMarkedSent:
    async def test_nudge_marked_sent(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """After delivery, nudge.status == 'sent' and delivered_at is set."""
        ws = _make_workspace({"delivery_channels": ["push"]})
        nudge = _make_nudge(workspace_id=ws.id)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_result(ws),
                _scalar_result([_make_membership(_make_user())]),
            ]
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.services.nudges.nudge_delivery.push_notification_service"
        ) as mock_push:
            mock_push.send_to_workspace_members = AsyncMock()

            await delivery.deliver_nudge(mock_db, nudge)

        assert nudge.status == "sent"
        assert nudge.delivered_at is not None
        assert "push" in nudge.delivered_via


class TestAssignedUserOnly:
    async def test_assigned_user_only(
        self, delivery: NudgeDeliveryService
    ) -> None:
        """Nudge with assigned_to_user_id → only that user is targeted."""
        ws = _make_workspace({"delivery_channels": ["push"]})
        assigned_user = _make_user(user_id=99)
        nudge = _make_nudge(workspace_id=ws.id, assigned_to_user_id=99)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_result(ws),
                _scalar_one_result(assigned_user),  # resolve single user
            ]
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.services.nudges.nudge_delivery.push_notification_service"
        ) as mock_push:
            mock_push.send_to_user = AsyncMock()

            result = await delivery.deliver_nudge(mock_db, nudge)

        assert result is True
        mock_push.send_to_user.assert_awaited_once()
        assert nudge.status == "sent"
