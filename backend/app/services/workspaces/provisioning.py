"""Personal workspace provisioning for new/first-login users.

A freshly-registered :class:`~app.models.user.User` with no
:class:`~app.models.workspace.WorkspaceMembership` leaves the frontend with
``default_workspace_id=null`` and ``currentWorkspace=null``, which freezes every
workspace-scoped page on its loading skeleton (finding RF-001). This module
guarantees every user lands in a usable default workspace that mirrors
:func:`app.api.v1.workspaces.create_workspace`: an owner membership plus a
default pipeline via :func:`ensure_default_pipeline`.

:func:`ensure_personal_workspace` is idempotent and flushes but does not commit
— the caller owns the transaction.
"""

from __future__ import annotations

import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.services.opportunities import ensure_default_pipeline
from app.services.workspaces.membership import (
    add_membership,
    get_default_membership,
    lock_memberships,
)

logger = structlog.get_logger()


def _slugify(value: str) -> str:
    """Reduce ``value`` to the workspace slug charset (``^[a-z0-9-]+$``)."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


def _workspace_name(user: User) -> str:
    """Pick a friendly personal-workspace name from the user's identity."""
    if user.full_name and user.full_name.strip():
        first = user.full_name.strip().split()[0]
        return f"{first}'s Workspace"
    return "My Workspace"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Return a globally-unique slug derived from ``base``.

    The ``workspaces.slug`` column is globally unique, so a personal workspace
    cannot reuse another tenant's slug. We try the base slug first, then append a
    short random suffix until free.
    """
    base = _slugify(base) or "workspace"
    slug = base
    while True:
        existing = await db.execute(select(Workspace.id).where(Workspace.slug == slug))
        if existing.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{uuid.uuid4().hex[:6]}"


async def ensure_personal_workspace(db: AsyncSession, user: User) -> Workspace:
    """Return the user's default workspace, creating a personal one if absent.

    Idempotent: if the user already has an active membership, their effective
    default workspace is returned unchanged. Otherwise a personal workspace
    with an owner membership and a default pipeline is provisioned. Flushes but
    does not commit; the caller owns the transaction.
    """
    await lock_memberships(db, user.id)
    existing = await get_default_membership(db, user.id)
    if existing is not None:
        workspace = await db.get(Workspace, existing.workspace_id)
        if workspace is not None:
            return workspace

    name = _workspace_name(user)
    slug = await _unique_slug(db, name)
    workspace = Workspace(name=name, slug=slug)
    db.add(workspace)
    await db.flush()

    await add_membership(db, user_id=user.id, workspace_id=workspace.id, role="owner")

    # Mirror create_workspace: provision a default pipeline so the opportunities
    # board renders and the promotion flow has a pipeline to open into.
    await ensure_default_pipeline(db, workspace.id)
    await db.flush()

    logger.info(
        "personal_workspace_provisioned",
        user_id=user.id,
        workspace_id=str(workspace.id),
        slug=slug,
    )
    return workspace
