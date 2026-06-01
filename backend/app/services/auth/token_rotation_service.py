"""Access/refresh token issuance and rotation service."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    revoke_refresh_token,
    store_refresh_token,
    validate_refresh_token,
)
from app.models.user import User


@dataclass(slots=True, frozen=True)
class AuthTokenPair:
    """Access token plus its paired refresh token."""

    access_token: str
    refresh_token: str


class TokenRotationService:
    """Issue, rotate, and revoke auth tokens."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def issue_pair(self, user: User) -> AuthTokenPair:
        """Create and persist a new access/refresh token pair for a user."""
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(days=settings.refresh_token_expire_days),
        )

        refresh_payload = decode_refresh_token(refresh_token)
        if refresh_payload and refresh_payload.get("jti"):
            await store_refresh_token(
                self.db,
                user_id=user.id,
                jti=refresh_payload["jti"],
                expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=UTC),
            )

        return AuthTokenPair(access_token=access_token, refresh_token=refresh_token)

    async def rotate_refresh_token(self, refresh_token: str) -> AuthTokenPair:
        """Validate a refresh token, revoke it, and mint a replacement pair."""
        payload = self._decode_refresh_or_raise(refresh_token)
        user_id = self._payload_user_id_or_raise(payload)
        old_jti = self._payload_jti(payload)
        if old_jti is None or not await validate_refresh_token(self.db, old_jti, user_id):
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = await self._active_user_or_raise(user_id)
        await revoke_refresh_token(self.db, old_jti)
        return await self.issue_pair(user)

    async def revoke_from_refresh_token(self, refresh_token: str) -> bool:
        """Revoke the refresh token JTI if it decodes successfully.

        Returns True when a token was revoked so callers can commit only on a
        persisted change.
        """
        payload = decode_refresh_token(refresh_token)
        if not payload:
            return False
        jti = self._payload_jti(payload)
        if jti is None:
            return False
        await revoke_refresh_token(self.db, jti)
        return True

    def _decode_refresh_or_raise(self, refresh_token: str) -> dict[str, Any]:
        payload = decode_refresh_token(refresh_token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    def _payload_user_id_or_raise(self, payload: dict[str, Any]) -> int:
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        try:
            return int(user_id_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            ) from exc

    def _payload_jti(self, payload: dict[str, Any]) -> str | None:
        jti = payload.get("jti")
        if not isinstance(jti, str) or not jti:
            return None
        return jti

    async def _active_user_or_raise(self, user_id: int) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )

        return user
