"""Device token endpoints for push notification registration."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models.device_token import DeviceToken

router = APIRouter()


class RegisterTokenRequest(BaseModel):
    """Schema for registering an Expo push token."""

    expo_push_token: str
    device_name: str | None = None
    platform: str | None = None


class RegisterTokenResponse(BaseModel):
    """Schema for token registration response."""

    id: str
    expo_push_token: str
    device_name: str | None
    platform: str | None


@router.post("/device-tokens", response_model=RegisterTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device_token(
    body: RegisterTokenRequest,
    current_user: CurrentUser,
    db: DB,
) -> RegisterTokenResponse:
    """Register or update an Expo push token for the current user."""
    # Check if token already exists
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.expo_push_token == body.expo_push_token)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Reassign to current user if needed, update metadata
        existing.user_id = current_user.id
        existing.device_name = body.device_name
        existing.platform = body.platform
        await db.commit()
        await db.refresh(existing)
        return RegisterTokenResponse(
            id=str(existing.id),
            expo_push_token=existing.expo_push_token,
            device_name=existing.device_name,
            platform=existing.platform,
        )

    # Create new token
    token = DeviceToken(
        user_id=current_user.id,
        expo_push_token=body.expo_push_token,
        device_name=body.device_name,
        platform=body.platform,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    return RegisterTokenResponse(
        id=str(token.id),
        expo_push_token=token.expo_push_token,
        device_name=token.device_name,
        platform=token.platform,
    )


@router.delete("/device-tokens/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device_token(
    token: str,
    current_user: CurrentUser,
    db: DB,
) -> Response:
    """Unregister an Expo push token."""
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.expo_push_token == token,
            DeviceToken.user_id == current_user.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
