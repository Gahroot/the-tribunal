"""HTTP cookie helpers for auth tokens."""

from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600
ACCESS_COOKIE_NAME = "access_token"
# Access cookie is needed across the entire API surface, not just /auth.
ACCESS_COOKIE_PATH = "/"


class AuthCookieService:
    """Manage browser auth cookies on FastAPI responses."""

    def set_refresh_cookie(self, response: Response, token: str) -> None:
        """Set the refresh token as an httpOnly cookie on the response."""
        response.set_cookie(
            REFRESH_COOKIE_NAME,
            token,
            httponly=True,
            secure=settings.secure_auth_cookies,
            samesite="lax",
            max_age=REFRESH_COOKIE_MAX_AGE,
            path=REFRESH_COOKIE_PATH,
        )

    def clear_refresh_cookie(self, response: Response) -> None:
        """Clear the refresh token cookie."""
        response.delete_cookie(
            REFRESH_COOKIE_NAME,
            path=REFRESH_COOKIE_PATH,
        )

    def set_access_cookie(self, response: Response, token: str) -> None:
        """Set the access token as an httpOnly cookie on the response.

        Mirrors the refresh-token pattern: httpOnly + secure so JS in the browser
        cannot read or exfiltrate the token via XSS. ``samesite=lax`` blocks the
        cookie from being sent on most cross-site requests, which is the primary
        CSRF mitigation for state-changing endpoints.
        """
        response.set_cookie(
            ACCESS_COOKIE_NAME,
            token,
            httponly=True,
            secure=settings.secure_auth_cookies,
            samesite="lax",
            max_age=settings.access_token_expire_minutes * 60,
            path=ACCESS_COOKIE_PATH,
        )

    def clear_access_cookie(self, response: Response) -> None:
        """Clear the access token cookie."""
        response.delete_cookie(
            ACCESS_COOKIE_NAME,
            path=ACCESS_COOKIE_PATH,
        )

    def set_auth_cookies(
        self,
        response: Response,
        *,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """Set both auth cookies on a response."""
        self.set_access_cookie(response, access_token)
        self.set_refresh_cookie(response, refresh_token)

    def clear_auth_cookies(self, response: Response) -> None:
        """Clear both auth cookies from a response."""
        self.clear_access_cookie(response)
        self.clear_refresh_cookie(response)
