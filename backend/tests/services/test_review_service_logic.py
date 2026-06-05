"""Unit tests for ReviewService pure logic: the rating gate, SMS rendering,
sentiment bucketing, and reputation scoring.

These cover the negative-feedback firewall decision and reputation math without a
database — the DB-backed flow is exercised end-to-end by the live endpoint
probes documented in the goal run.
"""

import pytest

from app.models.review import ReviewSentiment
from app.schemas.review import ReviewSettings
from app.services.reviews.review_service import (
    ReviewService,
    _public_review_url,
    _sentiment_for_rating,
)


class _FakeContact:
    """Minimal stand-in for a Contact in body rendering."""

    def __init__(self, first_name: str | None) -> None:
        self.first_name = first_name


def _svc() -> ReviewService:
    """Build a ReviewService without invoking __init__ (no DB needed)."""
    return ReviewService.__new__(ReviewService)


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        (5, ReviewSentiment.POSITIVE),
        (4, ReviewSentiment.POSITIVE),
        (3, ReviewSentiment.NEUTRAL),
        (2, ReviewSentiment.NEGATIVE),
        (1, ReviewSentiment.NEGATIVE),
    ],
)
def test_sentiment_for_rating(rating: int, expected: ReviewSentiment) -> None:
    assert _sentiment_for_rating(rating) == expected


def test_public_review_url_prefers_google() -> None:
    settings = ReviewSettings(
        google_review_url="https://g.page/r/x",
        facebook_review_url="https://fb.com/x/reviews",
    )
    assert _public_review_url(settings) == "https://g.page/r/x"


def test_public_review_url_falls_back_to_facebook() -> None:
    settings = ReviewSettings(facebook_review_url="https://fb.com/x/reviews")
    assert _public_review_url(settings) == "https://fb.com/x/reviews"


def test_public_review_url_none_when_unset() -> None:
    assert _public_review_url(ReviewSettings()) is None


def test_render_request_body_default_template_includes_link_and_names() -> None:
    settings = ReviewSettings(enabled=True, business_name="Acme Plumbing")
    body = ReviewService._render_request_body(_svc(), settings, _FakeContact("Dana"), "TOK123")
    assert "Dana" in body
    assert "Acme Plumbing" in body
    assert "/p/reviews/TOK123" in body


def test_render_request_body_custom_template_appends_missing_link() -> None:
    settings = ReviewSettings(
        enabled=True,
        business_name="Acme",
        request_message_template="Hey {first_name}, rate us!",
    )
    body = ReviewService._render_request_body(_svc(), settings, _FakeContact("Dana"), "TOK999")
    assert body.startswith("Hey Dana, rate us!")
    # Link is force-appended even if the custom template omitted {link}.
    assert "/p/reviews/TOK999" in body


def test_render_request_body_missing_first_name_uses_fallback() -> None:
    settings = ReviewSettings(enabled=True, business_name="Acme")
    body = ReviewService._render_request_body(_svc(), settings, _FakeContact(None), "TOK")
    assert "there" in body


def test_reputation_score_zero_without_reviews() -> None:
    assert ReviewService._reputation_score(0.0, 0) == 0


def test_reputation_score_scales_and_dampens_low_volume() -> None:
    # A single 5-star review should not read as a perfect reputation.
    single = ReviewService._reputation_score(5.0, 1)
    assert single == 50  # (100) * (1/2)
    # The same average with more volume scores higher (confidence grows).
    many = ReviewService._reputation_score(5.0, 50)
    assert many > single
    assert many <= 100


def test_reputation_score_is_monotonic_in_average() -> None:
    low = ReviewService._reputation_score(2.0, 20)
    high = ReviewService._reputation_score(4.5, 20)
    assert high > low
