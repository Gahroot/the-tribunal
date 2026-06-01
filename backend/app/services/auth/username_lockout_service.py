"""Per-username failed-login lockout service."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_rate_limit import AuthRateLimit

# Max failed login attempts per *username* per 15-minute window. IP-based
# counters are insufficient on their own: a distributed attacker can rotate
# source IPs and brute-force a single account. Tracking failures by hashed
# username caps the total bad attempts an account can absorb regardless of how
# many source IPs the attacker controls.
USERNAME_LOCKOUT_LIMIT = 10
USERNAME_LOCKOUT_WINDOW_MINUTES = 15
LOGIN_FAILED_ENDPOINT = "login_failed"


def hash_username(username: str) -> str:
    """Return a SHA-256 hex digest of the lowercased username.

    Lowercased so case variations of the same email cannot bypass the lockout.
    Hashed so the rate-limit table never stores plaintext account identifiers.
    """
    return hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()


class UsernameLockoutService:
    """Track failed login attempts by hashed username."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def is_locked_out(self, username: str) -> bool:
        """Return True iff the account is currently locked out.

        Counts ``login_failed`` rows for this username's hash inside the rolling
        window. Callers must treat a True result like wrong credentials so a
        probe cannot tell whether the account exists.
        """
        window_start = datetime.now(UTC) - timedelta(minutes=USERNAME_LOCKOUT_WINDOW_MINUTES)
        username_hash = hash_username(username)

        count_result = await self.db.execute(
            select(func.count()).where(
                AuthRateLimit.username_hash == username_hash,
                AuthRateLimit.endpoint == LOGIN_FAILED_ENDPOINT,
                AuthRateLimit.created_at >= window_start,
            )
        )
        count = count_result.scalar() or 0
        return count >= USERNAME_LOCKOUT_LIMIT

    async def record_failure(self, *, username: str, client_ip: str) -> None:
        """Record a failed login attempt against the username's hash."""
        self.db.add(
            AuthRateLimit(
                client_ip=client_ip,
                endpoint=LOGIN_FAILED_ENDPOINT,
                username_hash=hash_username(username),
            )
        )
        await self.db.flush()
