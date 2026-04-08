"""Default drip sequence configurations for realtor lead reactivation.

Each step defines:
- step: Ordinal position (0-indexed)
- delay_days: Days to wait after the previous step before sending
- message: Template with {first_name} placeholder
- type: Step classification for analytics
"""

from datetime import time
from typing import Any

# ---------------------------------------------------------------------------
# Value-first realtor reactivation sequence (6 steps over ~60 days)
#
# Strategy: Lead with free value (market guide), build trust, then soft-ask
# for appointment. If no response after 6 touches, send breakup message.
# ---------------------------------------------------------------------------

REALTOR_REACTIVATION_STEPS: list[dict[str, Any]] = [
    {
        "step": 0,
        "delay_days": 0,
        "message": (
            "Hey {first_name}, it's been a while! The market's shifted a ton "
            "lately — I put together a quick guide on what's happening with "
            "home values in your area. Want me to send it over?"
        ),
        "type": "value_offer",
    },
    {
        "step": 1,
        "delay_days": 2,
        "message": (
            "Hey {first_name}, just following up — I've got that local market "
            "update ready if you're interested. No pressure at all!"
        ),
        "type": "gentle_follow_up",
    },
    {
        "step": 2,
        "delay_days": 5,
        "message": (
            "Hi {first_name}, quick heads up — homes in your area are moving "
            "fast right now. If you're curious what yours could go for, I can "
            "pull some comps. Just say the word!"
        ),
        "type": "value_drop",
    },
    {
        "step": 3,
        "delay_days": 7,
        "message": (
            "Hey {first_name}, I just helped a homeowner nearby get their "
            "place sold over asking. The market is really rewarding sellers "
            "right now. Let me know if you'd like to chat about your options!"
        ),
        "type": "social_proof",
    },
    {
        "step": 4,
        "delay_days": 16,
        "message": (
            "Hi {first_name}, I know it's been a bit — just wanted to check "
            "in. If you ever want to talk real estate, even just to know your "
            "options, I'm here. Want to grab a quick call?"
        ),
        "type": "soft_appointment_ask",
    },
    {
        "step": 5,
        "delay_days": 30,
        "message": (
            "Hey {first_name}, I don't want to be that person who keeps "
            "texting! This'll be my last reach-out for now. If you ever need "
            "anything real estate related, just text me back. Wishing you all "
            "the best!"
        ),
        "type": "breakup",
    },
]


def get_realtor_drip_config() -> dict[str, Any]:
    """Return a dict of DripCampaign fields for realtor lead reactivation.

    The caller is responsible for adding workspace_id, agent_id, and
    from_phone_number before persisting.
    """
    return {
        "name": "Dead Lead Reactivation",
        "description": (
            "Automated 6-step value-first sequence to re-engage dormant leads. "
            "Leads with market insights, builds trust, then soft-asks for appointment."
        ),
        "sequence_steps": REALTOR_REACTIVATION_STEPS,
        "sending_hours_start": time(9, 0),
        "sending_hours_end": time(19, 0),
        "sending_days": [0, 1, 2, 3, 4],  # Mon-Fri
        "timezone": "America/New_York",
        "messages_per_minute": 10,
    }
