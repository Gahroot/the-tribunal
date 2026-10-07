"""Campaign sending-window rule shared by workers and launch previews."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.core.sending_days import is_sending_day
from app.models.campaign import Campaign


def _as_time(value: time | datetime) -> time:
    # Some callers/tests hand datetimes; only the time-of-day matters.
    return value.time() if isinstance(value, datetime) else value


def is_within_sending_window(campaign: Campaign, now: datetime | None = None) -> bool:
    """Return whether ``now`` falls inside the campaign's sending days and hours.

    ``sending_days`` follows ``app.core.sending_days`` (Monday=0 … Sunday=6),
    evaluated on the campaign's local date. Missing hours mean "any time".
    """
    if campaign.sending_hours_start is None or campaign.sending_hours_end is None:
        return True

    local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo(campaign.timezone or "UTC"))
    if not is_sending_day(campaign.sending_days, local_now):
        return False

    start_time = _as_time(campaign.sending_hours_start)
    end_time = _as_time(campaign.sending_hours_end)
    return start_time <= local_now.time() <= end_time
