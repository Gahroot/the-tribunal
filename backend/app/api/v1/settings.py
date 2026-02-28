"""Settings endpoints for user profile, notifications, and workspace integrations."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser
from app.models.workspace import Workspace, WorkspaceIntegration, WorkspaceMembership
from app.schemas.user import (
    BusinessHoursSettings,
    BusinessHoursUpdate,
    CallForwardingSettings,
    CallForwardingUpdate,
    IntegrationsResponse,
    IntegrationStatus,
    NotificationSettings,
    NotificationSettingsUpdate,
    TeamMemberResponse,
    UserProfileResponse,
    UserProfileUpdate,
)

router = APIRouter()


# Known integration types with display names and descriptions
KNOWN_INTEGRATIONS = [
    {
        "integration_type": "calcom",
        "display_name": "Cal.com",
        "description": "Appointment scheduling",
    },
    {
        "integration_type": "telnyx",
        "display_name": "Telnyx",
        "description": "Voice & SMS provider",
    },
    {
        "integration_type": "sendgrid",
        "display_name": "SendGrid",
        "description": "Email delivery",
    },
    {
        "integration_type": "openai",
        "display_name": "OpenAI",
        "description": "AI models for agents",
    },
]


@router.get("/users/me/profile", response_model=UserProfileResponse)
async def get_profile(current_user: CurrentUser) -> UserProfileResponse:
    """Get current user's profile."""
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone_number=current_user.phone_number,
        timezone=current_user.timezone,
        created_at=current_user.created_at,
    )


@router.put("/users/me/profile", response_model=UserProfileResponse)
async def update_profile(
    profile_update: UserProfileUpdate,
    current_user: CurrentUser,
    db: DB,
) -> UserProfileResponse:
    """Update current user's profile."""
    if profile_update.full_name is not None:
        current_user.full_name = profile_update.full_name
    if profile_update.phone_number is not None:
        current_user.phone_number = profile_update.phone_number
    if profile_update.timezone is not None:
        current_user.timezone = profile_update.timezone

    await db.commit()
    await db.refresh(current_user)

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone_number=current_user.phone_number,
        timezone=current_user.timezone,
        created_at=current_user.created_at,
    )


@router.get("/users/me/notifications", response_model=NotificationSettings)
async def get_notifications(current_user: CurrentUser) -> NotificationSettings:
    """Get current user's notification settings."""
    return NotificationSettings(
        notification_email=current_user.notification_email,
        notification_sms=current_user.notification_sms,
        notification_push=current_user.notification_push,
        notification_push_calls=current_user.notification_push_calls,
        notification_push_messages=current_user.notification_push_messages,
        notification_push_voicemail=current_user.notification_push_voicemail,
    )


@router.put("/users/me/notifications", response_model=NotificationSettings)
async def update_notifications(
    notification_update: NotificationSettingsUpdate,
    current_user: CurrentUser,
    db: DB,
) -> NotificationSettings:
    """Update current user's notification settings."""
    if notification_update.notification_email is not None:
        current_user.notification_email = notification_update.notification_email
    if notification_update.notification_sms is not None:
        current_user.notification_sms = notification_update.notification_sms
    if notification_update.notification_push is not None:
        current_user.notification_push = notification_update.notification_push
    if notification_update.notification_push_calls is not None:
        current_user.notification_push_calls = notification_update.notification_push_calls
    if notification_update.notification_push_messages is not None:
        current_user.notification_push_messages = notification_update.notification_push_messages
    if notification_update.notification_push_voicemail is not None:
        current_user.notification_push_voicemail = notification_update.notification_push_voicemail

    await db.commit()
    await db.refresh(current_user)

    return NotificationSettings(
        notification_email=current_user.notification_email,
        notification_sms=current_user.notification_sms,
        notification_push=current_user.notification_push,
        notification_push_calls=current_user.notification_push_calls,
        notification_push_messages=current_user.notification_push_messages,
        notification_push_voicemail=current_user.notification_push_voicemail,
    )


@router.get("/workspaces/{workspace_id}/integrations", response_model=IntegrationsResponse)
async def get_integrations(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> IntegrationsResponse:
    """Get workspace integration statuses."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get existing integrations
    integrations_result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.is_active.is_(True),
        )
    )
    existing_integrations = {
        wi.integration_type for wi in integrations_result.scalars().all()
    }

    # Build response with known integrations
    integrations = []
    for known in KNOWN_INTEGRATIONS:
        integrations.append(
            IntegrationStatus(
                integration_type=known["integration_type"],
                is_connected=known["integration_type"] in existing_integrations,
                display_name=known["display_name"],
                description=known["description"],
            )
        )

    return IntegrationsResponse(integrations=integrations)


@router.get("/workspaces/{workspace_id}/team", response_model=list[TeamMemberResponse])
async def get_team_members(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[TeamMemberResponse]:
    """Get workspace team members."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get all members with user data
    result = await db.execute(
        select(WorkspaceMembership)
        .options(selectinload(WorkspaceMembership.user))
        .where(WorkspaceMembership.workspace_id == workspace_id)
    )
    memberships = result.scalars().all()

    return [
        TeamMemberResponse(
            id=m.user.id,
            email=m.user.email,
            full_name=m.user.full_name,
            role=m.role,
            created_at=m.created_at,
        )
        for m in memberships
    ]


@router.get("/workspaces/{workspace_id}/business-hours", response_model=BusinessHoursSettings)
async def get_business_hours(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> BusinessHoursSettings:
    """Get workspace business hours settings."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get workspace settings
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one()

    business_hours = workspace.settings.get("business_hours", {})
    return BusinessHoursSettings(**business_hours)


@router.put("/workspaces/{workspace_id}/business-hours", response_model=BusinessHoursSettings)
async def update_business_hours(
    workspace_id: uuid.UUID,
    update: BusinessHoursUpdate,
    current_user: CurrentUser,
    db: DB,
) -> BusinessHoursSettings:
    """Update workspace business hours settings."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get workspace
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one()

    # Merge update into settings
    current_settings = dict(workspace.settings)
    business_hours = current_settings.get("business_hours", {})

    update_data = update.model_dump(exclude_unset=True)
    if "schedule" in update_data:
        # Convert DaySchedule models to dicts
        update_data["schedule"] = {
            day: sched.model_dump() for day, sched in update.schedule.items()
        }
    business_hours.update(update_data)
    current_settings["business_hours"] = business_hours
    workspace.settings = current_settings

    await db.commit()
    await db.refresh(workspace)

    return BusinessHoursSettings(**workspace.settings.get("business_hours", {}))


@router.get("/workspaces/{workspace_id}/call-forwarding", response_model=CallForwardingSettings)
async def get_call_forwarding(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> CallForwardingSettings:
    """Get workspace call forwarding settings."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get workspace settings
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one()

    call_forwarding = workspace.settings.get("call_forwarding", {})
    return CallForwardingSettings(**call_forwarding)


@router.put("/workspaces/{workspace_id}/call-forwarding", response_model=CallForwardingSettings)
async def update_call_forwarding(
    workspace_id: uuid.UUID,
    update: CallForwardingUpdate,
    current_user: CurrentUser,
    db: DB,
) -> CallForwardingSettings:
    """Update workspace call forwarding settings."""
    # Verify workspace access
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get workspace
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one()

    # Merge update into settings
    current_settings = dict(workspace.settings)
    call_forwarding = current_settings.get("call_forwarding", {})

    update_data = update.model_dump(exclude_unset=True)
    call_forwarding.update(update_data)
    current_settings["call_forwarding"] = call_forwarding
    workspace.settings = current_settings

    await db.commit()
    await db.refresh(workspace)

    return CallForwardingSettings(**workspace.settings.get("call_forwarding", {}))
