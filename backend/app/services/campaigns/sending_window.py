"""Campaign sending-window rule shared by workers and launch previews."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.core.sending_days import is_sending_day
from app.models.campaign import Campaign


def _as_time(value: time | datetime) -> time:
    # Some callers/tests hand datetimes; only the time-of-day matters.
    return value.time() if isinstance(value, datetime) else value


def as_utc(value: datetime) -> datetime:
    """Compare instants in UTC; legacy naive stored timestamps are UTC, not host-local."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def has_scheduled_start_arrived(campaign: Campaign, now: datetime | None = None) -> bool:
    """The selected start is inclusive and applies to launch, resume, and every poll."""
    return campaign.scheduled_start is None or as_utc(now or datetime.now(UTC)) >= as_utc(
        campaign.scheduled_start
    )


def is_within_sending_window(campaign: Campaign, now: datetime | None = None) -> bool:
    """Return whether ``now`` is at/after start and inside sending days and hours.

    ``sending_days`` follows ``app.core.sending_days`` (Monday=0 … Sunday=6),
    evaluated on the campaign's local date. Missing hours mean "any time".
    """
    now = as_utc(now or datetime.now(UTC))
    if not has_scheduled_start_arrived(campaign, now):
        return False
    if campaign.sending_hours_start is None or campaign.sending_hours_end is None:
        return True

    local_now = now.astimezone(ZoneInfo(campaign.timezone or "UTC"))
    if not is_sending_day(campaign.sending_days, local_now):
        return False

    start_time = _as_time(campaign.sending_hours_start)
    end_time = _as_time(campaign.sending_hours_end)
    return start_time <= local_now.time() <= end_time
