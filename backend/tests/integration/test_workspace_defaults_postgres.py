"""RF-032 local-only PostgreSQL/HTTP checks, using an isolated fixture schema.

Run: uv run pytest -m integration tests/integration/test_workspace_defaults_postgres.py
Serve the same fixture for eyes: uv run python -m tests.integration.test_workspace_defaults_postgres
Never uses the configured application database; requires loopback tribunal_inbox_test.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api.deps import get_current_user, get_optional_current_user
from app.api.v1 import auth, billing, invitations, workspaces
from app.db.session import get_db
from app.models.agent import Agent
from app.models.invitation import WorkspaceInvitation
from app.models.pipeline import Pipeline, PipelineStage
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceIntegration, WorkspaceMembership
from app.services.workspaces.membership import add_membership, select_default_membership
from app.services.workspaces.provisioning import ensure_personal_workspace
from tests.integration.test_inbox_postgres import inbox_test_database_url

pytestmark = pytest.mark.integration


@asynccontextmanager
async def fixture_database():
    url = inbox_test_database_url()  # Rejects non-loopback and any other database name.
    schema = f"rf032_{uuid.uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            for model in (
                User,
                Workspace,
                WorkspaceMembership,
                WorkspaceInvitation,
                WorkspaceIntegration,
                Pipeline,
                PipelineStage,
                Agent,
            ):
                await connection.execute(
                    CreateTable(model.__table__, include_foreign_key_constraints=[])
                )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            db.add(
                User(
                    id=1, email="rf032@example.test", hashed_password="unused", full_name="Fixture"
                )
            )
            await db.commit()
        yield sessions
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def fixture_app(sessions):
    app = FastAPI()

    async def database():
        async with sessions() as db:
            yield db

    async def user():
        async with sessions() as db:
            return await db.get(User, 1)

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_optional_current_user] = user
    app.include_router(workspaces.router, prefix="/api/v1/workspaces")
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(invitations.public_router, prefix="/api/v1/invitations")
    return app


@pytest.fixture
async def sessions():
    async with fixture_database() as sessions:
        yield sessions


@pytest.fixture
async def client(sessions):
    async with AsyncClient(
        transport=ASGITransport(app=fixture_app(sessions)), base_url="http://fixture"
    ) as client:
        yield client


async def create_brand(client, slug):
    response = await client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def flags(sessions):
    async with sessions() as db:
        rows = (await db.execute(select(WorkspaceMembership))).scalars().all()
        return {m.workspace_id: m.is_default for m in rows}


async def test_first_second_creation_and_explicit_replacement(client, sessions):
    a = await create_brand(client, "brand-a")
    b = await create_brand(client, "brand-b")
    assert await flags(sessions) == {a: True, b: False}
    assert (await client.get("/api/v1/auth/me")).json()["default_workspace_id"] == str(a)
    response = await client.post(f"/api/v1/workspaces/{b}/set-default")
    assert response.status_code == 200, response.text
    assert response.json()["is_default"] is True
    assert await flags(sessions) == {a: False, b: True}
    assert (await client.get("/api/v1/auth/me")).json()["default_workspace_id"] == str(b)
    async with sessions() as db:
        for workspace_id in (a, b):
            assert (
                await db.execute(select(Pipeline).where(Pipeline.workspace_id == workspace_id))
            ).scalar_one()
            assert (
                await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))
            ).scalar_one()


@pytest.mark.parametrize("existing", [False, True])
async def test_invitation_defaults_only_first_membership(client, sessions, existing):
    a = await create_brand(client, "owned") if existing else None
    async with sessions() as db:
        workspace = Workspace(name="Invited", slug="invited")
        db.add(workspace)
        await db.flush()
        b = workspace.id
        db.add(
            WorkspaceInvitation(workspace_id=b, email="rf032@example.test", token="fixture-invite")
        )
        await db.commit()
    responses = await asyncio.gather(
        *[client.post("/api/v1/invitations/fixture-invite/accept") for _ in range(2)]
    )
    # The second request may observe the already-accepted invitation (400), or
    # have read it pending before waiting and take the already-member path (200).
    assert all(r.status_code in (200, 400) for r in responses), [
        (r.status_code, r.text) for r in responses
    ]
    assert any(r.status_code == 200 for r in responses)
    assert await flags(sessions) == ({a: True, b: False} if existing else {b: True})


async def test_legacy_duplicate_projection_and_billing_mapping_are_not_repaired(client, sessions):
    a = await create_brand(client, "legacy-a")
    b = await create_brand(client, "legacy-b")
    async with sessions() as db:
        rows = (await db.execute(select(WorkspaceMembership))).scalars().all()
        stamp = datetime(2026, 1, 1, tzinfo=UTC)
        for m in rows:
            m.is_default = True
            m.created_at = stamp if m.workspace_id == a else stamp + timedelta(days=1)
        integration = WorkspaceIntegration(workspace_id=a, integration_type="stripe")
        integration.credentials = {"customer_id": "cus_local_fixture"}
        db.add(integration)
        await db.commit()
        ciphertext = integration.encrypted_credentials
    listed = (await client.get("/api/v1/workspaces")).json()
    assert [row["is_default"] for row in listed] == [True, False]
    assert (await client.get("/api/v1/auth/me")).json()["default_workspace_id"] == str(a)
    c = await create_brand(client, "legacy-c")
    assert await flags(sessions) == {a: True, b: True, c: False}
    async with sessions() as db:
        user = await db.get(User, 1)
        authorized = AsyncMock(return_value=await db.get(Workspace, a))
        with patch.object(billing, "get_workspace_admin", authorized):
            assert await billing._get_user_workspace_id(user, db, None) == a
        authorized.assert_awaited_once()
        stored = (await db.execute(select(WorkspaceIntegration))).scalar_one()
        assert stored.encrypted_credentials == ciphertext
    assert (await client.post(f"/api/v1/workspaces/{b}/set-default")).status_code == 200
    assert await flags(sessions) == {a: False, b: True, c: False}
    async with sessions() as db:
        assert (
            await db.execute(select(WorkspaceIntegration))
        ).scalar_one().encrypted_credentials == ciphertext


async def test_concurrent_first_brands_and_default_changes(client, sessions):
    a, b = await asyncio.gather(create_brand(client, "race-a"), create_brand(client, "race-b"))
    assert sum((await flags(sessions)).values()) == 1
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/workspaces/{workspace_id}/set-default") for workspace_id in (a, b)]
    )
    assert all(r.status_code == 200 for r in responses)
    assert sum((await flags(sessions)).values()) == 1


async def test_concurrent_same_user_creation_retry_is_a_conflict_not_duplicate(client, sessions):
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/workspaces", json={"name": "Retry", "slug": "retry"})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 400]
    assert sum((await flags(sessions)).values()) == 1
    assert len(await flags(sessions)) == 1


async def test_user_lock_blocks_join_until_explicit_default_commits(client, sessions):
    a = await create_brand(client, "lock-a")
    b = await create_brand(client, "lock-b")
    async with sessions() as db:
        c_workspace = Workspace(name="Join", slug="join")
        db.add(c_workspace)
        await db.commit()
        c = c_workspace.id
    started = asyncio.Event()

    async def join():
        async with sessions() as db:
            started.set()
            await add_membership(db, user_id=1, workspace_id=c, role="member")
            await db.commit()

    async with sessions() as db:
        await select_default_membership(db, user_id=1, workspace_id=b)
        task = asyncio.create_task(join())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.15)
        await db.commit()
        await asyncio.wait_for(task, timeout=5)
    assert await flags(sessions) == {a: False, b: True, c: False}


async def test_concurrent_personal_provisioning_is_idempotent(sessions):
    async def provision():
        async with sessions() as db:
            user = await db.get(User, 1)
            workspace = await ensure_personal_workspace(db, user)
            await db.commit()
            return workspace.id

    a, b = await asyncio.gather(provision(), provision())
    assert a == b
    assert await flags(sessions) == {a: True}


async def test_failed_provisioning_rolls_back_brand_and_membership(sessions):
    async with sessions() as db:
        user = await db.get(User, 1)
        with (
            patch.object(
                workspaces,
                "ensure_default_agent",
                AsyncMock(side_effect=RuntimeError("fixture failure")),
            ),
            pytest.raises(RuntimeError, match="fixture failure"),
        ):
            await workspaces.create_workspace(
                workspaces.WorkspaceCreate(name="Failed", slug="failed"), user, db
            )
        await db.rollback()
        assert (await db.execute(select(Workspace))).scalars().all() == []
        assert (await db.execute(select(WorkspaceMembership))).scalars().all() == []
        assert (await db.execute(select(Pipeline))).scalars().all() == []


async def test_concurrent_brand_creation_and_invitation(client, sessions):
    async with sessions() as db:
        workspace = Workspace(name="Invited", slug="concurrent-invited")
        db.add(workspace)
        await db.flush()
        b = workspace.id
        db.add(
            WorkspaceInvitation(
                workspace_id=b, email="rf032@example.test", token="concurrent-invite"
            )
        )
        await db.commit()
    a, response = await asyncio.gather(
        create_brand(client, "concurrent-created"),
        client.post("/api/v1/invitations/concurrent-invite/accept"),
    )
    assert response.status_code == 200, response.text
    stored = await flags(sessions)
    assert set(stored) == {a, b}
    assert sum(stored.values()) == 1


@pytest.mark.parametrize("default_flags", [True, False])
async def test_legacy_timestamp_ties_and_zero_defaults(client, sessions, default_flags):
    a = await create_brand(client, "tie-a")
    b = await create_brand(client, "tie-b")
    async with sessions() as db:
        rows = (await db.execute(select(WorkspaceMembership))).scalars().all()
        for m in rows:
            m.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            m.is_default = default_flags
        expected = min(rows, key=lambda m: m.id).workspace_id
        await db.commit()
    listed = (await client.get("/api/v1/workspaces")).json()
    assert [row["workspace"]["id"] for row in listed if row["is_default"]] == [str(expected)]
    assert (await client.get("/api/v1/auth/me")).json()["default_workspace_id"] == str(expected)
    assert await flags(sessions) == {a: default_flags, b: default_flags}


async def test_inactive_default_uses_active_fallback_without_rewriting_flags(client, sessions):
    a = await create_brand(client, "inactive-a")
    b = await create_brand(client, "active-b")
    async with sessions() as db:
        workspace = await db.get(Workspace, a)
        workspace.is_active = False
        await db.commit()
        user = await db.get(User, 1)
        assert (await ensure_personal_workspace(db, user)).id == b
        await db.commit()
    listed = (await client.get("/api/v1/workspaces")).json()
    assert len(listed) == 1 and listed[0]["is_default"] is True
    assert listed[0]["workspace"]["id"] == str(b)
    assert (await client.get("/api/v1/auth/me")).json()["default_workspace_id"] == str(b)
    assert await flags(sessions) == {a: True, b: False}


async def test_set_default_does_not_grant_nonmember_access(client, sessions):
    a = await create_brand(client, "authorized")
    async with sessions() as db:
        foreign = Workspace(name="Foreign", slug="foreign")
        db.add(foreign)
        await db.commit()
        foreign_id = foreign.id
    response = await client.post(f"/api/v1/workspaces/{foreign_id}/set-default")
    # Existing workspace dependency deliberately hides nonmember workspaces.
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Workspace not found or access denied"
    assert await flags(sessions) == {a: True}


async def test_removing_flagged_member_replaces_default_atomically(client, sessions):
    a = await create_brand(client, "remove-a")
    b = await create_brand(client, "remove-b")
    async with sessions() as db:
        db.add(User(id=2, email="member@example.test", hashed_password="unused"))
        await db.flush()
        await add_membership(db, user_id=2, workspace_id=a, role="member")
        await add_membership(db, user_id=2, workspace_id=b, role="member")
        await db.commit()
    response = await client.delete(f"/api/v1/workspaces/{a}/members/2")
    assert response.status_code == 204, response.text
    async with sessions() as db:
        remaining = (
            await db.execute(select(WorkspaceMembership).where(WorkspaceMembership.user_id == 2))
        ).scalar_one()
        assert remaining.workspace_id == b
        assert remaining.is_default is True


if __name__ == "__main__":
    import uvicorn

    @asynccontextmanager
    async def lifespan(app):
        async with fixture_database() as sessions:
            fixture = fixture_app(sessions)
            app.dependency_overrides.update(fixture.dependency_overrides)
            yield

    app = fixture_app(None)
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=8032)
