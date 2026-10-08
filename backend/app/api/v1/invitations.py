"""Workspace invitation endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.crud import get_nested_or_404
from app.api.deps import DB, CurrentUser, OptionalCurrentUser
from app.core.config import settings
from app.db.scope import apply_workspace_scope
from app.models.invitation import (
    WorkspaceInvitation,
    default_expires_at,
    generate_invitation_token,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.invitation import (
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationEmailStatus,
    InvitationPublicResponse,
    InvitationResponse,
)
from app.services.email import email_delivery_configured, send_invitation_email
from app.services.idempotency import derive_outbound_key
from app.services.workspaces.membership import add_membership, lock_memberships

router = APIRouter()
logger = structlog.get_logger()

# A resend of an email the provider already accepted is throttled so a
# double-click (or an impatient admin) cannot spam the recipient. Failed or
# unconfigured deliveries can be retried immediately.
RESEND_COOLDOWN = timedelta(seconds=60)


def _invitation_response(
    inv: WorkspaceInvitation,
    *,
    invited_by_email: str | None,
    invited_by_name: str | None,
) -> InvitationResponse:
    """Serialize an invitation for admins. Never includes the token."""
    email_status: InvitationEmailStatus = "unknown"
    if inv.email_status in ("sent", "failed", "not_configured"):
        email_status = inv.email_status  # type: ignore[assignment]
    return InvitationResponse(
        id=inv.id,
        workspace_id=inv.workspace_id,
        email=inv.email,
        role=inv.role,
        status=inv.status,
        message=inv.message,
        invited_by_email=invited_by_email,
        invited_by_name=invited_by_name,
        expires_at=inv.expires_at,
        created_at=inv.created_at,
        accepted_at=inv.accepted_at,
        is_expired=inv.is_expired,
        email_status=email_status,
        email_attempt_count=inv.email_attempt_count or 0,
        email_last_attempt_at=inv.email_last_attempt_at,
        email_sent_at=inv.email_sent_at,
    )


async def _deliver_invitation_email(
    invitation: WorkspaceInvitation,
    *,
    token: str,
    workspace_name: str,
    inviter_name: str,
) -> InvitationEmailStatus:
    """Make one delivery attempt and record its real outcome on the invitation.

    Only an explicit ``True`` from the sender counts as sent; ``False``, a
    raised error, or missing email configuration are recorded as not sent.
    The caller commits. Each attempt gets its own provider idempotency key so a
    deliberate resend is not deduplicated away by the provider, while a retry
    of the same attempt still is.
    """
    now = datetime.now(UTC)
    invitation.email_attempt_count = (invitation.email_attempt_count or 0) + 1
    invitation.email_last_attempt_at = now

    if not email_delivery_configured():
        invitation.email_status = "not_configured"
        logger.warning(
            "invitation_email_not_configured",
            invitation_id=str(invitation.id),
            workspace_id=str(invitation.workspace_id),
        )
        return "not_configured"

    sent = False
    try:
        sent = await send_invitation_email(
            to_email=invitation.email,
            workspace_name=workspace_name,
            inviter_name=inviter_name,
            invitation_url=f"{settings.frontend_url}/invite/{token}",
            role=invitation.role,
            message=invitation.message,
            idempotency_key=derive_outbound_key(
                "workspace_invitation_email",
                invitation.id,
                invitation.email_attempt_count,
            ),
        )
    except Exception as exc:
        # Log the error type only: provider errors can echo request params,
        # which include the secret acceptance link.
        logger.error(
            "invitation_email_send_error",
            invitation_id=str(invitation.id),
            error_type=type(exc).__name__,
        )
        sent = False

    if sent is True:
        invitation.email_status = "sent"
        invitation.email_sent_at = now
        return "sent"

    invitation.email_status = "failed"
    logger.warning(
        "invitation_email_not_sent",
        invitation_id=str(invitation.id),
        workspace_id=str(invitation.workspace_id),
        attempt=invitation.email_attempt_count,
    )
    return "failed"


async def verify_workspace_admin(
    db: DB,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> WorkspaceMembership:
    """Verify user has admin access to workspace."""
    result = await db.execute(
        apply_workspace_scope(select(WorkspaceMembership), WorkspaceMembership, workspace_id).where(
            WorkspaceMembership.user_id == current_user.id
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to manage invitations",
        )

    return membership


@router.get("", response_model=list[InvitationResponse])
async def list_invitations(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[InvitationResponse]:
    """List all pending invitations for a workspace."""
    await verify_workspace_admin(db, current_user, workspace_id)

    result = await db.execute(
        apply_workspace_scope(
            select(WorkspaceInvitation).options(selectinload(WorkspaceInvitation.invited_by)),
            WorkspaceInvitation,
            workspace_id,
        )
        .where(WorkspaceInvitation.status == "pending")
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    invitations = result.scalars().all()

    return [
        _invitation_response(
            inv,
            invited_by_email=inv.invited_by.email if inv.invited_by else None,
            invited_by_name=inv.invited_by.full_name if inv.invited_by else None,
        )
        for inv in invitations
    ]


@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    workspace_id: uuid.UUID,
    invitation_data: InvitationCreate,
    current_user: CurrentUser,
    db: DB,
) -> InvitationResponse:
    """Create an invitation, then attempt to email it.

    The invitation is persisted before delivery so a provider outage never
    loses it. The response reports the real delivery outcome in
    ``email_status``; anything other than ``"sent"`` should be retried via
    ``POST /{invitation_id}/resend`` rather than by creating a new invitation.
    """
    await verify_workspace_admin(db, current_user, workspace_id)

    # Get workspace details
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check if user is already a member
    result = await db.execute(select(User).where(User.email == invitation_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        result = await db.execute(
            apply_workspace_scope(
                select(WorkspaceMembership), WorkspaceMembership, workspace_id
            ).where(WorkspaceMembership.user_id == existing_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this workspace",
            )

    # Check for an existing pending invitation (case-insensitive, matching how
    # acceptance compares emails). An expired one no longer blocks a re-invite.
    pending_result = await db.execute(
        apply_workspace_scope(select(WorkspaceInvitation), WorkspaceInvitation, workspace_id).where(
            func.lower(WorkspaceInvitation.email) == invitation_data.email.lower(),
            WorkspaceInvitation.status == "pending",
        )
    )
    for existing_invitation in pending_result.scalars().all():
        if not existing_invitation.is_expired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "An invitation is already pending for this email. "
                    "Resend it from the pending invitations list."
                ),
            )
        existing_invitation.status = "expired"

    # Create invitation
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        email=invitation_data.email,
        role=invitation_data.role,
        message=invitation_data.message,
        invited_by_id=current_user.id,
    )
    db.add(invitation)
    # Commit before sending so the invitation survives a provider failure.
    await db.commit()
    await db.refresh(invitation)

    email_status = await _deliver_invitation_email(
        invitation,
        token=invitation.token,
        workspace_name=workspace.name,
        inviter_name=current_user.full_name or current_user.email,
    )
    await db.commit()

    logger.info(
        "invitation_created",
        workspace_id=str(workspace_id),
        invitation_id=str(invitation.id),
        invited_by=current_user.id,
        email_status=email_status,
    )

    return _invitation_response(
        invitation,
        invited_by_email=current_user.email,
        invited_by_name=current_user.full_name,
    )


@router.post("/{invitation_id}/resend", response_model=InvitationResponse)
async def resend_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> InvitationResponse:
    """Re-attempt email delivery for an existing pending invitation.

    Reuses the same invitation (no duplicate is created). If it has expired,
    a fresh token and expiry are issued, but only persisted once the new email
    was actually sent, so a failed resend never invalidates a working link.
    """
    await verify_workspace_admin(db, current_user, workspace_id)

    result = await db.execute(
        apply_workspace_scope(
            select(WorkspaceInvitation).options(selectinload(WorkspaceInvitation.invited_by)),
            WorkspaceInvitation,
            workspace_id,
        )
        .where(WorkspaceInvitation.id == invitation_id)
        .with_for_update(of=WorkspaceInvitation)
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resend pending invitations",
        )

    now = datetime.now(UTC)
    if (
        invitation.email_status == "sent"
        and invitation.email_last_attempt_at is not None
        and now - invitation.email_last_attempt_at < RESEND_COOLDOWN
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This invitation was just sent. Please wait a minute before resending.",
        )

    workspace_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    invited_by_email = invitation.invited_by.email if invitation.invited_by else None
    invited_by_name = invitation.invited_by.full_name if invitation.invited_by else None

    renew = invitation.is_expired
    token = generate_invitation_token() if renew else invitation.token

    email_status = await _deliver_invitation_email(
        invitation,
        token=token,
        workspace_name=workspace.name,
        inviter_name=current_user.full_name or current_user.email,
    )
    if renew and email_status == "sent":
        invitation.token = token
        invitation.expires_at = default_expires_at()
    await db.commit()

    logger.info(
        "invitation_resent",
        invitation_id=str(invitation.id),
        workspace_id=str(workspace_id),
        resent_by=current_user.id,
        renewed=renew and email_status == "sent",
        email_status=email_status,
    )

    return _invitation_response(
        invitation,
        invited_by_email=invited_by_email,
        invited_by_name=invited_by_name,
    )


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Cancel a pending invitation."""
    await verify_workspace_admin(db, current_user, workspace_id)

    invitation = await get_nested_or_404(
        db,
        WorkspaceInvitation,
        invitation_id,
        parent_field="workspace_id",
        parent_id=workspace_id,
        detail="Invitation not found",
    )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel pending invitations",
        )

    invitation.status = "cancelled"
    await db.commit()

    logger.info(
        "invitation_cancelled",
        invitation_id=str(invitation_id),
        cancelled_by=current_user.id,
    )


# Public endpoints for invitation acceptance (outside workspace scope)
public_router = APIRouter()


@public_router.get("/{token}", response_model=InvitationPublicResponse)
async def get_invitation_by_token(
    token: str,
    db: DB,
) -> InvitationPublicResponse:
    """Get invitation details by token (public endpoint)."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.invited_by),
        )
        .where(WorkspaceInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    return InvitationPublicResponse(
        workspace_name=invitation.workspace.name,
        workspace_slug=invitation.workspace.slug,
        email=invitation.email,
        role=invitation.role,
        invited_by_name=invitation.invited_by.full_name if invitation.invited_by else None,
        expires_at=invitation.expires_at,
        is_expired=invitation.is_expired,
        is_valid=invitation.is_valid,
    )


@public_router.post("/{token}/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    token: str,
    current_user: OptionalCurrentUser,
    db: DB,
) -> InvitationAcceptResponse:
    """Accept an invitation to join a workspace."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .options(selectinload(WorkspaceInvitation.workspace))
        .where(WorkspaceInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if not invitation.is_valid:
        if invitation.is_expired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has expired",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is no longer valid",
        )

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to accept this invitation",
        )

    # Verify email matches (case insensitive)
    if current_user.email.lower() != invitation.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email address",
        )

    # Serialize acceptance with brand creation/default changes and duplicate
    # acceptance requests before checking membership.
    await lock_memberships(db, current_user.id)
    # Check if already a member
    result = await db.execute(
        apply_workspace_scope(
            select(WorkspaceMembership),
            WorkspaceMembership,
            invitation.workspace_id,
        ).where(WorkspaceMembership.user_id == current_user.id)
    )
    if result.scalar_one_or_none():
        # Already a member, just mark invitation as accepted
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(UTC)
        await db.commit()

        return InvitationAcceptResponse(
            success=True,
            message="You are already a member of this workspace",
            workspace_id=invitation.workspace_id,
            workspace_slug=invitation.workspace.slug,
        )

    # Create membership
    await add_membership(
        db,
        user_id=current_user.id,
        workspace_id=invitation.workspace_id,
        role=invitation.role,
    )

    # Update invitation status
    invitation.status = "accepted"
    invitation.accepted_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "invitation_accepted",
        invitation_id=str(invitation.id),
        user_id=current_user.id,
        workspace_id=str(invitation.workspace_id),
    )

    return InvitationAcceptResponse(
        success=True,
        message=f"You have joined {invitation.workspace.name}",
        workspace_id=invitation.workspace_id,
        workspace_slug=invitation.workspace.slug,
    )
