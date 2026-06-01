"""WebSocket ticket issuance service."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, Protocol

from app.core.security import create_access_token
from app.models.user import User
from app.services.rate_limiting.auth_limiter import enforce_ws_ticket_rate_limit

EnforceWsTicketRateLimit = Callable[[int], Awaitable[None]]


class CreateAccessToken(Protocol):
    """Callable shape for access-token creation."""

    def __call__(
        self,
        data: dict[str, Any],
        expires_delta: timedelta | None = None,
    ) -> str: ...


class WebSocketTicketService:
    """Issue short-lived JWT tickets for WebSocket authentication."""

    def __init__(
        self,
        *,
        enforce_rate_limit_func: EnforceWsTicketRateLimit = enforce_ws_ticket_rate_limit,
        create_access_token_func: CreateAccessToken = create_access_token,
    ) -> None:
        self.enforce_rate_limit = enforce_rate_limit_func
        self.create_access_token = create_access_token_func

    async def issue_ticket(self, user: User) -> str:
        """Issue a one-minute ticket JWT for a current authenticated user."""
        await self.enforce_rate_limit(user.id)
        return self.create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=1),
        )
