"""10DLC trust tier configurations."""

from typing import TypedDict


class TrustTierConfig(TypedDict):
    """Configuration for a 10DLC trust tier."""

    name: str
    daily_limit: int
    hourly_limit: int
    messages_per_second: float
    description: str


TRUST_TIERS: dict[str, TrustTierConfig] = {
    "low_volume": {
        "name": "Low Volume (Lowest Tier)",
        "daily_limit": 75,
        "hourly_limit": 10,
        "messages_per_second": 1.0,
        "description": "10DLC lowest trust tier, strict limits",
    },
    "standard": {
        "name": "Standard Brand (With Fees)",
        "daily_limit": 2000,
        "hourly_limit": 200,
        "messages_per_second": 3.0,
        "description": "10DLC with carrier fees paid",
    },
    "high_volume": {
        "name": "High Volume Verified",
        "daily_limit": 10000,
        "hourly_limit": 1000,
        "messages_per_second": 10.0,
        "description": "Verified brand with high throughput",
    },
}


def get_trust_tier_config(tier: str) -> TrustTierConfig:
    """Get configuration for a trust tier.

    Args:
        tier: Trust tier name (low_volume, standard, high_volume)

    Returns:
        Trust tier configuration

    Raises:
        KeyError: If tier is not found
    """
    return TRUST_TIERS[tier]


def get_default_limits(tier: str) -> tuple[int, int, float]:
    """Get default rate limits for a trust tier.

    Args:
        tier: Trust tier name

    Returns:
        Tuple of (daily_limit, hourly_limit, messages_per_second)
    """
    config = get_trust_tier_config(tier)
    return config["daily_limit"], config["hourly_limit"], config["messages_per_second"]
