"""Database-backed IP rate limits for unauthenticated auth endpoints."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit_helpers import raise_rate_limited
from app.models.auth_rate_limit import AuthRateLimit

# Max auth attempts per IP per 15-minute window.
AUTH_RATE_LIMIT = 10
AUTH_RATE_WINDOW_MINUTES = 15


def _seconds_until_window_clears(
    oldest_created_at: datetime | None,
    window_seconds: int,
    now: datetime,
) -> int:
    """Compute seconds until a rolling database rate-limit window has room."""
    if oldest_created_at is None:
        return window_seconds
    if oldest_created_at.tzinfo is None:
        oldest_created_at = oldest_created_at.replace(tzinfo=UTC)
    expires_at = oldest_created_at + timedelta(seconds=window_seconds)
    remaining = int((expires_at - now).total_seconds())
    return max(1, remaining)


class AuthIpRateLimitService:
    """Enforce IP-based auth rate limits."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def enforce(self, *, client_ip: str, endpoint: str) -> None:
        """Record and enforce the IP limit for an auth endpoint."""
        now = datetime.now(UTC)
        window_seconds = AUTH_RATE_WINDOW_MINUTES * 60
        window_start = now - timedelta(seconds=window_seconds)

        # Pull the oldest in-window record alongside the count so we can compute
        # a precise ``Retry-After`` instead of a flat 15-minute default.
        count_result = await self.db.execute(
            select(func.count(), func.min(AuthRateLimit.created_at)).where(
                AuthRateLimit.client_ip == client_ip,
                AuthRateLimit.endpoint == endpoint,
                AuthRateLimit.created_at >= window_start,
            )
        )
        row = count_result.one()
        count = row[0] or 0
        oldest = row[1]

        if count >= AUTH_RATE_LIMIT:
            retry_after = _seconds_until_window_clears(oldest, window_seconds, now)
            raise_rate_limited(
                retry_after,
                detail="Too many requests. Please try again later.",
            )

        rate_limit_record = AuthRateLimit(client_ip=client_ip, endpoint=endpoint)
        self.db.add(rate_limit_record)
        await self.db.flush()
