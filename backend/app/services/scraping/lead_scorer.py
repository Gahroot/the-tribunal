"""Lead scoring service for ranking enriched business contacts."""

from typing import Any


def estimate_revenue_tier(business_intel: dict[str, Any]) -> str:  # noqa: PLR0912
    """Estimate revenue tier from business signals.

    Returns: "Under $500K" | "$500K-$1M" | "$1M-$5M" | "$5M+" | "Unknown"
    """
    revenue_points = 0

    # Team size signal
    website_summary: dict[str, Any] = business_intel.get("website_summary", {})
    team_size = website_summary.get("team_size_estimate", "unknown")
    team_size_map = {
        "solo": 0,
        "small (2-5)": 5,
        "medium (6-20)": 15,
        "large (20+)": 25,
    }
    revenue_points += team_size_map.get(team_size, 0)

    # Ad pixel signals
    ad_pixels: dict[str, bool] = business_intel.get("ad_pixels", {})
    if ad_pixels.get("meta_pixel"):
        revenue_points += 10
    if ad_pixels.get("google_ads"):
        revenue_points += 10

    # Reviews signal
    google_places: dict[str, Any] = business_intel.get("google_places", {})
    review_count = google_places.get("review_count", 0)
    if review_count > 200:
        revenue_points += 10
    elif review_count > 50:
        revenue_points += 5

    # Financing signal
    if website_summary.get("has_financing"):
        revenue_points += 10

    # Revenue signals
    if website_summary.get("revenue_signals"):
        revenue_points += 15

    # Certifications signal
    if website_summary.get("certifications"):
        revenue_points += 10

    # Service areas signal
    service_areas = website_summary.get("service_areas", [])
    if len(service_areas) > 5:
        revenue_points += 5

    # Years in business signal
    years = website_summary.get("years_in_business")
    if years is not None and years >= 10:
        revenue_points += 10
    elif years is not None and years >= 5:
        revenue_points += 5

    # Social media signal
    social_links: dict[str, Any] = business_intel.get("social_links", {})
    social_count = sum(1 for v in social_links.values() if v)
    if social_count >= 4:
        revenue_points += 5

    # Map points to tier
    if revenue_points >= 60:
        return "$5M+"
    if revenue_points >= 40:
        return "$1M-$5M"
    if revenue_points >= 25:
        return "$500K-$1M"
    if revenue_points >= 10:
        return "Under $500K"
    return "Unknown"


def compute_lead_score_breakdown(  # noqa: PLR0912, PLR0915
    business_intel: dict[str, Any],
) -> dict[str, Any]:
    """Compute lead score with detailed breakdown for UI display.

    Returns dict with:
        - score: int (total score)
        - revenue_tier: str
        - breakdown: dict of category -> points
        - decision_maker_name: str | None
        - decision_maker_title: str | None
    """
    breakdown: dict[str, int] = {}
    score = 0

    # Ad pixel signals
    ad_pixel_points = 0
    ad_pixels: dict[str, bool] = business_intel.get("ad_pixels", {})
    if ad_pixels.get("meta_pixel"):
        ad_pixel_points += 25
    if ad_pixels.get("google_ads"):
        ad_pixel_points += 25
    if ad_pixels.get("google_analytics"):
        ad_pixel_points += 5
    if ad_pixels.get("gtm"):
        ad_pixel_points += 5
    breakdown["ad_pixels"] = ad_pixel_points
    score += ad_pixel_points

    # Google Places signals
    google_presence_points = 0
    google_places: dict[str, Any] = business_intel.get("google_places", {})
    rating = google_places.get("rating")
    if rating is not None and rating >= 4.0:
        google_presence_points += 10
    review_count = google_places.get("review_count", 0)
    if review_count > 50:
        google_presence_points += 10
    if review_count > 200:
        google_presence_points += 10
    breakdown["google_presence"] = google_presence_points
    score += google_presence_points

    # Website presence
    website_points = 0
    website_meta: dict[str, Any] = business_intel.get("website_meta", {})
    if website_meta.get("title") or website_meta.get("description"):
        website_points += 5
    breakdown["website"] = website_points
    score += website_points

    # Website summary signals
    website_summary: dict[str, Any] = business_intel.get("website_summary", {})

    team_size = website_summary.get("team_size_estimate", "unknown")
    team_size_points = 0
    if team_size in ("medium (6-20)", "large (20+)"):
        team_size_points = 15
    elif team_size == "small (2-5)":
        team_size_points = 8
    breakdown["team_size"] = team_size_points
    score += team_size_points

    financing_points = 10 if website_summary.get("has_financing") else 0
    breakdown["financing"] = financing_points
    score += financing_points

    revenue_signal_points = 15 if website_summary.get("revenue_signals") else 0
    breakdown["revenue_signals"] = revenue_signal_points
    score += revenue_signal_points

    cert_points = 10 if website_summary.get("certifications") else 0
    breakdown["certifications"] = cert_points
    score += cert_points

    # Social media presence
    social_links: dict[str, Any] = business_intel.get("social_links", {})
    social_count = sum(1 for v in social_links.values() if v)
    social_points = min(social_count * 3, 15)
    breakdown["social_media"] = social_points
    score += social_points

    # Revenue tier bonus
    revenue_tier = estimate_revenue_tier(business_intel)
    tier_bonus_map = {"$5M+": 20, "$1M-$5M": 15, "$500K-$1M": 10}
    tier_bonus = tier_bonus_map.get(revenue_tier, 0)
    breakdown["revenue_tier"] = tier_bonus
    score += tier_bonus

    # Decision maker bonus
    decision_maker_name = website_summary.get("decision_maker_name")
    decision_maker_title = website_summary.get("decision_maker_title")
    dm_points = 10 if decision_maker_name else 0
    breakdown["decision_maker"] = dm_points
    score += dm_points

    return {
        "score": score,
        "revenue_tier": revenue_tier,
        "breakdown": breakdown,
        "decision_maker_name": decision_maker_name,
        "decision_maker_title": decision_maker_title,
    }


def compute_lead_score(business_intel: dict[str, Any]) -> int:  # noqa: PLR0912
    """Compute a lead score (0-~190) based on business intelligence signals.

    Scoring rubric:
        Ad pixels: Meta +25, Google Ads +25, GA +5, GTM +5
        Google presence: rating >= 4.0 +10, reviews > 50 +10, reviews > 200 +10
        Website: has website +5
        Team: medium/large +15, small +8
        Financing: +10
        Social media: +3 per platform (max +15)
        Revenue signals: +15 if any found
        Certifications: +10 if any found
        Revenue tier bonus: $5M+ +20, $1M-$5M +15, $500K-$1M +10
        Decision maker: +10 if found
    """
    result = compute_lead_score_breakdown(business_intel)
    return int(result["score"])
