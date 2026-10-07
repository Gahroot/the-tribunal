from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from tribunal_reviews.models import (
    Review,
    ReviewRequest,
    ReviewRequestChannel,
    ReviewRequestStatus,
)
from tribunal_reviews.schemas import PublicReviewNextStep
from tribunal_reviews.service import ReviewService

from app.models.workspace import Workspace


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
    monkeypatch.setattr("tribunal_reviews.service.emit_automation_event", emit)

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
    monkeypatch.setattr("tribunal_reviews.service.emit_automation_event", emit)

    result = await service.submit_rating("rating-token", 5)

    assert result.success is True
    assert result.is_positive is True
    assert result.redirect_url == public_url
    assert result.public_review_destination_missing is False
    assert result.show_feedback_form is False
    assert result.message == "Thanks! Redirecting you to leave a public review."


# --------------------------------------------------------------------------- #
# Reopening a link after rating (RF-019)                                       #
# --------------------------------------------------------------------------- #

PUBLIC_URL = "https://g.page/r/acme/review"


def _rated_request(workspace_id: uuid.UUID, rating: int, status: ReviewRequestStatus):
    review_request = _review_request(workspace_id)
    review_request.rating = rating
    review_request.status = status
    return review_request


def _review(*, is_public: bool, body: str | None = None) -> Review:
    return Review(id=uuid.uuid4(), rating=5 if is_public else 2, is_public=is_public, body=body)


def _service_for(workspace: Workspace, review_request: ReviewRequest, review: Review | None):
    db = MagicMock(commit=AsyncMock())
    service = ReviewService(db)
    service._load_request_by_token = AsyncMock(return_value=review_request)  # type: ignore[method-assign]
    service._load_workspace = AsyncMock(return_value=workspace)  # type: ignore[method-assign]
    service._load_contact = AsyncMock(return_value=MagicMock(first_name="Dana"))  # type: ignore[method-assign]
    service._load_review_for_request = AsyncMock(return_value=review)  # type: ignore[method-assign]
    service._upsert_review_for_request = AsyncMock()  # type: ignore[method-assign]
    service._notify_review = AsyncMock()  # type: ignore[method-assign]
    return service, db


async def test_reopen_unrated_link_asks_for_rating() -> None:
    workspace = _workspace_with_review_settings({"enabled": True})
    service, _ = _service_for(workspace, _review_request(workspace.id), None)

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.RATE
    assert result.already_submitted is False


async def test_reopen_after_positive_rating_offers_public_handoff_again() -> None:
    workspace = _workspace_with_review_settings({"enabled": True, "google_review_url": PUBLIC_URL})
    request = _rated_request(workspace.id, 5, ReviewRequestStatus.COMPLETED)
    service, _ = _service_for(workspace, request, _review(is_public=True))

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.PUBLIC_REVIEW
    assert result.redirect_url == PUBLIC_URL
    assert result.feedback_submitted is False
    # Clicking through is not proof a review was posted.
    assert result.message is not None and "posted" not in result.message.lower()


async def test_reopen_after_positive_rating_without_destination_is_done() -> None:
    workspace = _workspace_with_review_settings({"enabled": True})
    request = _rated_request(workspace.id, 5, ReviewRequestStatus.COMPLETED)
    service, _ = _service_for(workspace, request, _review(is_public=True))

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.DONE
    assert result.redirect_url is None
    assert result.public_review_destination_missing is True


async def test_reopen_after_low_rating_resumes_feedback_form() -> None:
    workspace = _workspace_with_review_settings({"enabled": True, "google_review_url": PUBLIC_URL})
    request = _rated_request(workspace.id, 2, ReviewRequestStatus.RATED)
    service, _ = _service_for(workspace, request, _review(is_public=False))

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.FEEDBACK
    # Low ratings never get the public handoff (firewall preserved).
    assert result.redirect_url is None


async def test_reopen_after_feedback_shows_acknowledgement_only() -> None:
    workspace = _workspace_with_review_settings({"enabled": True, "google_review_url": PUBLIC_URL})
    request = _rated_request(workspace.id, 2, ReviewRequestStatus.COMPLETED)
    service, _ = _service_for(workspace, request, _review(is_public=False, body="Late"))

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.DONE
    assert result.feedback_submitted is True
    assert result.redirect_url is None


async def test_routing_uses_recorded_decision_not_current_threshold() -> None:
    # Rated 4 when threshold was 4 (public); threshold since raised to 5.
    workspace = _workspace_with_review_settings(
        {"enabled": True, "positive_threshold": 5, "google_review_url": PUBLIC_URL}
    )
    request = _rated_request(workspace.id, 4, ReviewRequestStatus.COMPLETED)
    service, _ = _service_for(workspace, request, _review(is_public=True))

    result = await service.get_public_request("tok")

    assert result.next_step == PublicReviewNextStep.PUBLIC_REVIEW


async def test_repeat_rating_keeps_original_rating_and_routing(monkeypatch) -> None:
    workspace = _workspace_with_review_settings({"enabled": True, "google_review_url": PUBLIC_URL})
    request = _rated_request(workspace.id, 2, ReviewRequestStatus.RATED)
    service, _ = _service_for(workspace, request, _review(is_public=False))
    emit = AsyncMock()
    monkeypatch.setattr("tribunal_reviews.service.emit_automation_event", emit)

    result = await service.submit_rating("tok", 5)

    assert result.rating == 2
    assert result.is_positive is False
    assert result.redirect_url is None
    assert result.show_feedback_form is True
    assert request.rating == 2
    emit.assert_not_awaited()
    service._notify_review.assert_not_awaited()


async def test_repeat_rating_after_feedback_does_not_reopen_form(monkeypatch) -> None:
    workspace = _workspace_with_review_settings({"enabled": True})
    request = _rated_request(workspace.id, 1, ReviewRequestStatus.COMPLETED)
    service, _ = _service_for(workspace, request, _review(is_public=False, body="Rude"))
    monkeypatch.setattr("tribunal_reviews.service.emit_automation_event", AsyncMock())

    result = await service.submit_rating("tok", 1)

    assert result.show_feedback_form is False
    assert result.feedback_submitted is True


async def test_repeat_feedback_does_not_overwrite_original() -> None:
    workspace = _workspace_with_review_settings({"enabled": True})
    request = _rated_request(workspace.id, 2, ReviewRequestStatus.COMPLETED)
    review = _review(is_public=False, body="Original")
    service, db = _service_for(workspace, request, review)

    stored = await service.submit_feedback("tok", "Second attempt", "Dana")

    assert stored is False
    assert review.body == "Original"
    db.commit.assert_not_awaited()


async def test_first_feedback_is_stored_and_completes_request() -> None:
    workspace = _workspace_with_review_settings({"enabled": True})
    request = _rated_request(workspace.id, 2, ReviewRequestStatus.RATED)
    review = _review(is_public=False)
    service, db = _service_for(workspace, request, review)

    stored = await service.submit_feedback("tok", "x" * 5000, None)

    assert stored is True
    assert review.body == "x" * 5000
    assert request.status == ReviewRequestStatus.COMPLETED
    db.commit.assert_awaited_once()
