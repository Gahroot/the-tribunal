"""Workspace endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
    WorkspaceWithMembership,
)

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
