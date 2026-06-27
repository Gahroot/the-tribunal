"""Tests for bulk workspace-member creation.

A workspace owner/admin can provision many team logins in one batch. Each input
row resolves to exactly one outcome (created / added_existing / already_member /
skipped); a conflicting row must not poison the rest of the batch.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.encryption import hash_value
from app.core.security import get_password_hash, verify_password
from app.db.session import AsyncSessionLocal, engine
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.bulk_members import BulkMemberItem
from app.services.workspaces import bulk_create_members

# Hits the real database (integration; run with `-m integration`).
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
async def _fresh_engine_pool():
    """Dispose the shared engine pool around each test (loop-affinity safety)."""
    await engine.dispose()
    yield
    await engine.dispose()


async def _make_workspace(db) -> Workspace:
    ws = Workspace(id=uuid.uuid4(), name="Shop", slug=f"shop-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    await db.flush()
    return ws


def _email() -> str:
    return f"bulk-{uuid.uuid4().hex[:10]}@example.com"


async def test_bulk_create_creates_new_users_with_default_membership() -> None:
    async with AsyncSessionLocal() as db:
        ws = await _make_workspace(db)
        emails = [_email(), _email()]
        items = [
            BulkMemberItem(email=emails[0], full_name="Tech One", role="technician"),
            BulkMemberItem(email=emails[1], role="dispatcher", password="caller-set-pw"),
        ]

        result = await bulk_create_members(db, workspace_id=ws.id, caller_role="owner", items=items)
        await db.flush()

        assert result.total == 2
        assert result.created == 2
        assert result.skipped == 0

        by_email = {r.email: r for r in result.results}
        # Generated password surfaced once for the row without a password.
        assert by_email[emails[0].lower()].temporary_password is not None
        # Caller-supplied password is never echoed back.
        assert by_email[emails[1].lower()].temporary_password is None

        # New accounts default into THIS workspace so first login lands here.
        for email in emails:
            user = (
                await db.execute(select(User).where(User.email_hash == hash_value(email)))
            ).scalar_one()
            membership = (
                await db.execute(
                    select(WorkspaceMembership).where(
                        WorkspaceMembership.user_id == user.id,
                        WorkspaceMembership.workspace_id == ws.id,
                    )
                )
            ).scalar_one()
            assert membership.is_default is True

        # The generated temporary password actually authenticates.
        tech_user = (
            await db.execute(select(User).where(User.email_hash == hash_value(emails[0])))
        ).scalar_one()
        assert verify_password(
            by_email[emails[0].lower()].temporary_password, tech_user.hashed_password
        )
        # Both created accounts (generated AND caller-supplied password) are
        # flagged to force a password reset on first login.
        for email in emails:
            created = (
                await db.execute(select(User).where(User.email_hash == hash_value(email)))
            ).scalar_one()
            assert created.must_change_password is True


async def test_bulk_attaches_existing_user_without_touching_password() -> None:
    async with AsyncSessionLocal() as db:
        ws = await _make_workspace(db)
        email = _email()
        original_hash = get_password_hash("original-secret")
        existing = User(email=email, hashed_password=original_hash, full_name="Already Here")
        db.add(existing)
        await db.flush()

        result = await bulk_create_members(
            db,
            workspace_id=ws.id,
            caller_role="owner",
            items=[BulkMemberItem(email=email, role="sales_rep", password="ignored-pw")],
        )
        await db.flush()

        assert result.added_existing == 1
        row = result.results[0]
        assert row.status == "added_existing"
        assert row.user_id == existing.id
        assert row.temporary_password is None

        # Password untouched, and an existing account is never force-reset by
        # being attached to another workspace.
        await db.refresh(existing)
        assert existing.hashed_password == original_hash
        assert existing.must_change_password is False

        membership = (
            await db.execute(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.user_id == existing.id,
                    WorkspaceMembership.workspace_id == ws.id,
                )
            )
        ).scalar_one()
        assert membership.role == "sales_rep"
        assert membership.is_default is False


async def test_bulk_reports_already_member_and_intra_request_duplicate() -> None:
    async with AsyncSessionLocal() as db:
        ws = await _make_workspace(db)
        email = _email()
        existing = User(email=email, hashed_password=get_password_hash("x"))
        db.add(existing)
        await db.flush()
        db.add(
            WorkspaceMembership(
                user_id=existing.id, workspace_id=ws.id, role="member", is_default=False
            )
        )
        await db.flush()

        dup_email = _email()
        result = await bulk_create_members(
            db,
            workspace_id=ws.id,
            caller_role="owner",
            items=[
                BulkMemberItem(email=email, role="member"),
                BulkMemberItem(email=dup_email, role="technician"),
                BulkMemberItem(email=dup_email, role="technician"),
            ],
        )
        await db.flush()

        assert result.already_member == 1
        assert result.created == 1
        assert result.skipped == 1  # the second dup_email row
        statuses = {r.email: r.status for r in result.results}
        assert statuses[email.lower()] == "already_member"


async def test_admin_caller_cannot_grant_admin_role() -> None:
    async with AsyncSessionLocal() as db:
        ws = await _make_workspace(db)
        email = _email()

        result = await bulk_create_members(
            db,
            workspace_id=ws.id,
            caller_role="admin",
            items=[BulkMemberItem(email=email, role="admin")],
        )
        await db.flush()

        assert result.created == 0
        assert result.skipped == 1
        assert result.results[0].status == "skipped"
        assert "owner" in (result.results[0].error or "").lower()

        # No user account was created for the rejected row.
        created = (
            await db.execute(select(User).where(User.email_hash == hash_value(email)))
        ).scalar_one_or_none()
        assert created is None


async def test_owner_caller_can_grant_admin_role() -> None:
    async with AsyncSessionLocal() as db:
        ws = await _make_workspace(db)
        email = _email()

        result = await bulk_create_members(
            db,
            workspace_id=ws.id,
            caller_role="owner",
            items=[BulkMemberItem(email=email, role="admin")],
        )
        await db.flush()

        assert result.created == 1
        membership = (
            await db.execute(
                select(WorkspaceMembership)
                .join(User, User.id == WorkspaceMembership.user_id)
                .where(
                    User.email_hash == hash_value(email),
                    WorkspaceMembership.workspace_id == ws.id,
                )
            )
        ).scalar_one()
        assert membership.role == "admin"
