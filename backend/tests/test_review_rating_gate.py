from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.review_request import ReviewRequest, ReviewRequestChannel, ReviewRequestStatus
from app.models.workspace import Workspace
from app.services.reviews.review_service import ReviewService


def _workspace_with_review_settings(settings: dict[str, object]) -> Workspace:
    return Workspace(
        id=uuid.uuid4(),
        name="Acme Realty",
        slug=f"acme-{uuid.uuid4().hex[:8]}",
        settings={"review_settings": settings},
        is_active=True,
    )


def _review_request(workspace_id: uuid.UUID) -> ReviewRequest:
    return ReviewRequest(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        contact_id=123,
        token="rating-token",
        channel=ReviewRequestChannel.SMS,
        status=ReviewRequestStatus.CLICKED,
    )


async def test_positive_rating_signals_missing_public_destination(monkeypatch) -> None:
    workspace = _workspace_with_review_settings({"enabled": True, "positive_threshold": 4})
    review_request = _review_request(workspace.id)
    service = ReviewService(MagicMock(commit=AsyncMock()))
    service._load_request_by_token = AsyncMock(return_value=review_request)  # type: ignore[method-assign]
    service._load_workspace = AsyncMock(return_value=workspace)  # type: ignore[method-assign]
    service._upsert_review_for_request = AsyncMock()  # type: ignore[method-assign]
    service._notify_review = AsyncMock()  # type: ignore[method-assign]
    emit = AsyncMock()
    monkeypatch.setattr("app.services.reviews.review_service.emit_automation_event", emit)

    result = await service.submit_rating("rating-token", 5)

    assert result.success is True
    assert result.is_positive is True
    assert result.redirect_url is None
    assert result.public_review_destination_missing is True
    assert result.show_feedback_form is False
    assert "recorded" in result.message


async def test_positive_rating_returns_public_destination(monkeypatch) -> None:
    public_url = "https://g.page/r/acme/review"
    workspace = _workspace_with_review_settings(
        {
            "enabled": True,
            "positive_threshold": 4,
            "google_review_url": public_url,
        }
    )
    review_request = _review_request(workspace.id)
    service = ReviewService(MagicMock(commit=AsyncMock()))
    service._load_request_by_token = AsyncMock(return_value=review_request)  # type: ignore[method-assign]
    service._load_workspace = AsyncMock(return_value=workspace)  # type: ignore[method-assign]
    service._upsert_review_for_request = AsyncMock()  # type: ignore[method-assign]
    service._notify_review = AsyncMock()  # type: ignore[method-assign]
    emit = AsyncMock()
    monkeypatch.setattr("app.services.reviews.review_service.emit_automation_event", emit)

    result = await service.submit_rating("rating-token", 5)

    assert result.success is True
    assert result.is_positive is True
    assert result.redirect_url == public_url
    assert result.public_review_destination_missing is False
    assert result.show_feedback_form is False
    assert result.message == "Thanks! Redirecting you to leave a public review."
