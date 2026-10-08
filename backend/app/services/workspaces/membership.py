"""Per-user membership/default policy. Callers own the transaction.

Lock the user, not existing memberships: the first membership has no row to
lock. All membership writers must take this lock before reading or changing
membership state. Legacy flags are only normalized by an explicit set-default;
reads never repair data or change historical Stripe account mappings.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership


async def lock_memberships(db: AsyncSession, user_id: int) -> None:
    """Serialize membership writes, including concurrent first memberships."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


async def get_default_membership(db: AsyncSession, user_id: int) -> WorkspaceMembership | None:
    """One effective active default: oldest flagged, else oldest membership.

    UUID breaks timestamp ties. This projection is shared by login and the
    workspace list; it does not mutate legacy duplicate/zero-default rows.
    Billing deliberately retains its separate historical resolver.
    """
    result = await db.execute(
        select(WorkspaceMembership)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == user_id, Workspace.is_active.is_(True))
        .order_by(
            WorkspaceMembership.is_default.desc(),
            WorkspaceMembership.created_at.asc(),
            WorkspaceMembership.id.asc(),
        )
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def add_membership(
    db: AsyncSession, *, user_id: int, workspace_id: uuid.UUID, role: str
) -> WorkspaceMembership:
    """Idempotently join without replacing an existing default.

    Only the first membership receives a stored default flag. Legacy users
    retain their flags until they explicitly select a default.
    """
    await lock_memberships(db, user_id)
    result = await db.execute(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    memberships = result.scalars().all()
    for membership in memberships:
        if membership.workspace_id == workspace_id:
            return membership
    membership = WorkspaceMembership(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        is_default=not memberships,
    )
    db.add(membership)
    await db.flush()
    return membership


async def select_default_membership(
    db: AsyncSession, *, user_id: int, workspace_id: uuid.UUID
) -> None:
    """Explicitly replace all flags atomically, after rechecking membership.

    Authorization of the active workspace stays at the route boundary. The
    membership is rechecked under the lock in case a concurrent removal won.
    """
    await lock_memberships(db, user_id)
    result = await db.execute(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError("Workspace membership no longer exists")
    await db.execute(
        update(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user_id)
        .values(is_default=WorkspaceMembership.workspace_id == workspace_id)
    )
    await db.flush()
