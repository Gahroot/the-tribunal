"""Password-change service for authenticated users."""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, revoke_all_user_refresh_tokens, verify_password
from app.models.user import User
from app.schemas.user import ChangePasswordRequest
from app.services.rate_limiting.auth_limiter import enforce_change_password_rate_limit

VerifyPassword = Callable[[str, str], bool]
HashPassword = Callable[[str], str]
RevokeAllUserRefreshTokens = Callable[[AsyncSession, int], Awaitable[None]]
EnforcePasswordChangeRateLimit = Callable[[int], Awaitable[None]]


class PasswordChangeService:
    """Validate and apply a current-user password change."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        verify_password_func: VerifyPassword = verify_password,
        get_password_hash_func: HashPassword = get_password_hash,
        revoke_all_user_refresh_tokens_func: RevokeAllUserRefreshTokens = (
            revoke_all_user_refresh_tokens
        ),
        enforce_rate_limit_func: EnforcePasswordChangeRateLimit = (
            enforce_change_password_rate_limit
        ),
    ) -> None:
        self.db = db
        self.verify_password = verify_password_func
        self.get_password_hash = get_password_hash_func
        self.revoke_all_user_refresh_tokens = revoke_all_user_refresh_tokens_func
        self.enforce_rate_limit = enforce_rate_limit_func

    async def change_password(self, *, user: User, body: ChangePasswordRequest) -> None:
        """Change a user's password and revoke all refresh tokens.

        A per-user rate limit keeps a hijacked authenticated session from
        brute-forcing the current password. Revoking all refresh tokens forces
        every device to re-authenticate with the new password.
        """
        await self.enforce_rate_limit(user.id)

        if not self.verify_password(body.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        user.hashed_password = self.get_password_hash(body.new_password)
        # The user has now chosen their own password; lift any forced-reset gate
        # set at provisioning time (e.g. bulk member onboarding).
        user.must_change_password = False
        await self.revoke_all_user_refresh_tokens(self.db, user.id)
        await self.db.commit()
