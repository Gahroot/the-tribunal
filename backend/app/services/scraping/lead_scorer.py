"""Lead scoring service for ranking enriched business contacts."""

from typing import Any


def compute_lead_score(business_intel: dict[str, Any]) -> int:  # noqa: PLR0912
    """Compute a lead score (0-160) based on business intelligence signals.

    Scoring rubric:
        Ad pixels: Meta +25, Google Ads +25, GA +5, GTM +5
        Google presence: rating >= 4.0 +10, reviews > 50 +10, reviews > 200 +10
        Website: has website +5
        Team: medium/large +15, small +8
        Financing: +10
        Social media: +3 per platform (max +15)
        Revenue signals: +15 if any found
        Certifications: +10 if any found
    """
    score = 0

    # Ad pixel signals
    ad_pixels: dict[str, bool] = business_intel.get("ad_pixels", {})
    if ad_pixels.get("meta_pixel"):
        score += 25
    if ad_pixels.get("google_ads"):
        score += 25
    if ad_pixels.get("google_analytics"):
        score += 5
    if ad_pixels.get("gtm"):
        score += 5

    # Google Places signals
    google_places: dict[str, Any] = business_intel.get("google_places", {})
    rating = google_places.get("rating")
    if rating is not None and rating >= 4.0:
        score += 10
    review_count = google_places.get("review_count", 0)
    if review_count > 50:
        score += 10
    if review_count > 200:
        score += 10

    # Website presence
    website_meta: dict[str, Any] = business_intel.get("website_meta", {})
    if website_meta.get("title") or website_meta.get("description"):
        score += 5

    # Website summary signals
    website_summary: dict[str, Any] = business_intel.get("website_summary", {})
    team_size = website_summary.get("team_size_estimate", "unknown")
    if team_size in ("medium (6-20)", "large (20+)"):
        score += 15
    elif team_size == "small (2-5)":
        score += 8

    if website_summary.get("has_financing"):
        score += 10

    if website_summary.get("revenue_signals"):
        score += 15

    if website_summary.get("certifications"):
        score += 10

    # Social media presence
    social_links: dict[str, Any] = business_intel.get("social_links", {})
    social_count = sum(1 for v in social_links.values() if v)
    score += min(social_count * 3, 15)

    return score
