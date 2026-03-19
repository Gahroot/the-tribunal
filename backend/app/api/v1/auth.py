"""Authentication endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    verify_password,
)
from app.core.utils import get_client_ip
from app.db.session import get_db
from app.models.auth_rate_limit import AuthRateLimit
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.user import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserResponse,
    UserWithWorkspace,
)

router = APIRouter()

# Max auth attempts per IP per 15-minute window
_AUTH_RATE_LIMIT = 10
_AUTH_RATE_WINDOW_MINUTES = 15


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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Login and get access token."""
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
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires,
    )

    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Refresh access token using refresh token."""
    client_ip = get_client_ip(request, settings.trusted_proxies)
    await _check_auth_rate_limit(db, client_ip, "refresh")

    # Decode and validate refresh token
    payload = decode_refresh_token(refresh_request.refresh_token)
    if payload is None:
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

    # Create new access and refresh tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires,
    )

    await db.commit()

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, str]:
    """Change current user's password."""
    # Verify current password
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Update password
    current_user.hashed_password = get_password_hash(body.new_password)
    await db.commit()

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
