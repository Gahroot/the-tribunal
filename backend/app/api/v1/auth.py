"""Authentication endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    password_needs_rehash,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token,
    store_refresh_token,
    validate_refresh_token,
    verify_password,
)
from app.core.utils import get_client_ip
from app.db.session import get_db
from app.models.auth_rate_limit import AuthRateLimit
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.user import (
    ChangePasswordRequest,
    Token,
    UserCreate,
    UserResponse,
    UserWithWorkspace,
)

router = APIRouter()

# Max auth attempts per IP per 15-minute window
_AUTH_RATE_LIMIT = 10
_AUTH_RATE_WINDOW_MINUTES = 15

_REFRESH_COOKIE_PATH = "/api/v1/auth"
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an httpOnly cookie on the response."""
    response.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path=_REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        "refresh_token",
        path=_REFRESH_COOKIE_PATH,
    )


async def _check_auth_rate_limit(db: AsyncSession, client_ip: str, endpoint: str) -> None:
    """Check IP-based rate limit for authentication endpoints.

    Args:
        db: Database session
        client_ip: Client IP address
        endpoint: The endpoint being accessed (login, register, refresh)

    Raises:
        HTTPException: If rate limit exceeded
    """
    window_start = datetime.now(UTC) - timedelta(minutes=_AUTH_RATE_WINDOW_MINUTES)

    count_result = await db.execute(
        select(func.count()).where(
            AuthRateLimit.client_ip == client_ip,
            AuthRateLimit.endpoint == endpoint,
            AuthRateLimit.created_at >= window_start,
        )
    )
    count = count_result.scalar() or 0

    if count >= _AUTH_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    # Record this attempt
    rate_limit_record = AuthRateLimit(client_ip=client_ip, endpoint=endpoint)
    db.add(rate_limit_record)
    await db.flush()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Register a new user."""
    client_ip = get_client_ip(request, settings.trusted_proxies)
    await _check_auth_rate_limit(db, client_ip, "register")

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Login and get access token.

    The access_token is returned in the JSON body (short-lived, stored in memory).
    The refresh_token is set as an httpOnly cookie (not exposed to JS).
    """
    client_ip = get_client_ip(request, settings.trusted_proxies)
    await _check_auth_rate_limit(db, client_ip, "login")

    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Transparently upgrade legacy bcrypt hashes to Argon2id on successful login
    if password_needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(form_data.password)
        await db.flush()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # Create access and refresh tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
    refresh_tok = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires,
    )

    # Store refresh token hash in DB for server-side tracking
    refresh_payload = decode_refresh_token(refresh_tok)
    if refresh_payload and refresh_payload.get("jti"):
        await store_refresh_token(
            db,
            user_id=user.id,
            jti=refresh_payload["jti"],
            expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=UTC),
        )

    await db.commit()

    # Set refresh token as httpOnly cookie
    _set_refresh_cookie(response, refresh_tok)

    return Token(access_token=access_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Refresh access token using the refresh_token httpOnly cookie."""
    client_ip = get_client_ip(request, settings.trusted_proxies)
    await _check_auth_rate_limit(db, client_ip, "refresh")

    # Read refresh token from httpOnly cookie
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode and validate refresh token
    payload = decode_refresh_token(refresh_token_value)
    if payload is None:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user ID from token
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_id = int(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        ) from exc

    # Validate refresh token against DB (checks revocation + reuse detection)
    old_jti = payload.get("jti")
    if not old_jti or not await validate_refresh_token(db, old_jti, user_id):
        _clear_refresh_cookie(response)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
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

    # Revoke the old refresh token (rotation)
    await revoke_refresh_token(db, old_jti)

    # Create new access and refresh tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
    new_refresh_tok = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires,
    )

    # Store new refresh token hash in DB
    new_payload = decode_refresh_token(new_refresh_tok)
    if new_payload and new_payload.get("jti"):
        await store_refresh_token(
            db,
            user_id=user.id,
            jti=new_payload["jti"],
            expires_at=datetime.fromtimestamp(new_payload["exp"], tz=UTC),
        )

    await db.commit()

    # Rotate refresh token cookie
    _set_refresh_cookie(response, new_refresh_tok)

    return Token(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Logout by revoking the refresh token and clearing the cookie."""
    refresh_token_value = request.cookies.get("refresh_token")
    if refresh_token_value:
        payload = decode_refresh_token(refresh_token_value)
        if payload and payload.get("jti"):
            await revoke_refresh_token(db, payload["jti"])
            await db.commit()

    _clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, str]:
    """Change current user's password.

    Revokes all existing refresh tokens to force re-authentication
    on all devices.
    """
    # Verify current password
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Update password
    current_user.hashed_password = get_password_hash(body.new_password)

    # Revoke all refresh tokens for this user
    await revoke_all_user_refresh_tokens(db, current_user.id)

    await db.commit()

    # Clear the current session's refresh cookie
    _clear_refresh_cookie(response)

    return {"message": "Password updated successfully"}


@router.get("/me", response_model=UserWithWorkspace)
async def get_me(current_user: CurrentUser, db: DB) -> dict[str, Any]:
    """Get current user info with default workspace."""
    # Get default workspace (use first() in case multiple are marked as default)
    result = await db.execute(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.is_default.is_(True),
        )
        .limit(1)
    )
    membership = result.scalar_one_or_none()

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
        "default_workspace_id": str(membership.workspace_id) if membership else None,
    }
