"""Workspace endpoints."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
    WorkspaceWithMembership,
)


class UpdateMemberRoleRequest(BaseModel):
    """Request to update a member's role."""

    role: Literal["admin", "member"]


class MemberResponse(BaseModel):
    """Response for member operations."""

    user_id: int
    role: str
    message: str

router = APIRouter()


@router.get("", response_model=list[WorkspaceWithMembership])
async def list_workspaces(
    current_user: CurrentUser,
    db: DB,
) -> list[WorkspaceWithMembership]:
    """List all workspaces the user is a member of."""
    result = await db.execute(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == current_user.id)
        .order_by(WorkspaceMembership.created_at)
    )
    memberships = result.scalars().all()

    workspaces_with_membership = []
    for membership in memberships:
        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == membership.workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        if workspace and workspace.is_active:
            workspaces_with_membership.append(
                WorkspaceWithMembership(
                    workspace=WorkspaceResponse.model_validate(workspace),
                    role=membership.role,
                    is_default=membership.is_default,
                )
            )

    return workspaces_with_membership


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_in: WorkspaceCreate,
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceResponse:
    """Create a new workspace."""
    # Check if slug already exists
    result = await db.execute(select(Workspace).where(Workspace.slug == workspace_in.slug))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace slug already exists",
        )

    # Create workspace
    workspace = Workspace(
        name=workspace_in.name,
        slug=workspace_in.slug,
        description=workspace_in.description,
        settings=workspace_in.settings,
    )
    db.add(workspace)
    await db.flush()

    # Create membership (owner)
    membership = WorkspaceMembership(
        user_id=current_user.id,
        workspace_id=workspace.id,
        role="owner",
        is_default=True,
    )
    db.add(membership)

    await db.commit()
    await db.refresh(workspace)

    return WorkspaceResponse.model_validate(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceResponse:
    """Get a specific workspace."""
    # Verify membership
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # Get workspace
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace: Workspace | None = ws_result.scalar_one_or_none()

    if workspace is None or not workspace.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    return WorkspaceResponse.model_validate(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    workspace_in: WorkspaceUpdate,
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceResponse:
    """Update a workspace (owner/admin only)."""
    # Verify membership with admin+ role
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role.in_(["owner", "admin"]),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this workspace",
        )

    # Get workspace
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace: Workspace | None = ws_result.scalar_one_or_none()

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Update fields
    update_data = workspace_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(workspace, field, value)

    await db.commit()
    await db.refresh(workspace)

    return WorkspaceResponse.model_validate(workspace)


@router.post("/{workspace_id}/set-default", response_model=WorkspaceWithMembership)
async def set_default_workspace(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceWithMembership:
    """Set a workspace as the user's default workspace."""
    # Verify membership
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
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace: Workspace | None = ws_result.scalar_one_or_none()
    if workspace is None or not workspace.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Clear is_default for all other memberships of this user
    all_memberships_result = await db.execute(
        select(WorkspaceMembership).where(WorkspaceMembership.user_id == current_user.id)
    )
    for m in all_memberships_result.scalars().all():
        m.is_default = m.workspace_id == workspace_id

    await db.commit()
    await db.refresh(membership)

    return WorkspaceWithMembership(
        workspace=WorkspaceResponse.model_validate(workspace),
        role=membership.role,
        is_default=membership.is_default,
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete a workspace (owner only)."""
    # Verify ownership
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == "owner",
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can delete a workspace",
        )

    # Soft delete (deactivate)
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace: Workspace | None = ws_result.scalar_one_or_none()

    if workspace is not None:
        workspace.is_active = False
        await db.commit()


@router.put("/{workspace_id}/members/{user_id}/role", response_model=MemberResponse)
async def update_member_role(
    workspace_id: uuid.UUID,
    user_id: int,
    role_update: UpdateMemberRoleRequest,
    current_user: CurrentUser,
    db: DB,
) -> MemberResponse:
    """Update a member's role (owner/admin only)."""
    # Verify current user is owner or admin
    auth_result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role.in_(["owner", "admin"]),
        )
    )
    current_membership = auth_result.scalar_one_or_none()
    if current_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to manage members",
        )

    # Get target membership
    target_result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    target_membership = target_result.scalar_one_or_none()
    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this workspace",
        )

    # Cannot change owner's role
    if target_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change the owner's role",
        )

    # Admins cannot promote/demote other admins
    if current_membership.role == "admin" and target_membership.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot change other admins' roles",
        )

    # Update role
    target_membership.role = role_update.role
    await db.commit()

    return MemberResponse(
        user_id=user_id,
        role=role_update.role,
        message=f"Member role updated to {role_update.role}",
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: int,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Remove a member from the workspace (owner/admin only)."""
    # Verify current user is owner or admin
    auth_result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role.in_(["owner", "admin"]),
        )
    )
    current_membership = auth_result.scalar_one_or_none()
    if current_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to manage members",
        )

    # Get target membership
    target_result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    target_membership = target_result.scalar_one_or_none()
    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this workspace",
        )

    # Cannot remove the owner
    if target_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove the workspace owner",
        )

    # Admins cannot remove other admins
    if current_membership.role == "admin" and target_membership.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove other admins",
        )

    # Remove membership
    await db.delete(target_membership)
    await db.commit()
