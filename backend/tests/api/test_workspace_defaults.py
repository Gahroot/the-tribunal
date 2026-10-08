"""RF-032 contract tests; PostgreSQL races are covered in the integration suite."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.auth import get_me
from app.api.v1.workspaces import list_workspaces
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.workspaces.membership import add_membership, select_default_membership


def result(value=None, rows=()):
    response = MagicMock()
    response.scalar_one_or_none.return_value = value
    response.scalars.return_value.all.return_value = list(rows)
    response.all.return_value = list(rows)
    return response


def membership(*, default=True):
    return WorkspaceMembership(
        id=uuid.uuid4(), user_id=1, workspace_id=uuid.uuid4(), role="owner", is_default=default
    )


@pytest.mark.parametrize("existing", [False, True])
async def test_join_only_defaults_the_first_membership(existing):
    prior = membership()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(), result(rows=[prior] if existing else [])])
    db.flush = AsyncMock()
    joined = await add_membership(db, user_id=1, workspace_id=uuid.uuid4(), role="member")
    assert joined.is_default is (not existing)
    assert prior.is_default is True
    assert "FOR UPDATE" in str(db.execute.call_args_list[0].args[0])
    db.flush.assert_awaited_once()


async def test_duplicate_join_is_idempotent():
    prior = membership()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(), result(rows=[prior])])
    joined = await add_membership(db, user_id=1, workspace_id=prior.workspace_id, role="member")
    assert joined is prior
    db.add.assert_not_called()


async def test_explicit_default_locks_and_rechecks_before_update():
    db = AsyncMock()
    db.execute.side_effect = [result(), result(uuid.uuid4()), result()]
    target = uuid.uuid4()
    await select_default_membership(db, user_id=1, workspace_id=target)
    statements = [str(call.args[0]) for call in db.execute.call_args_list]
    assert "FOR UPDATE" in statements[0]
    assert "workspace_id" in statements[1]
    assert "UPDATE workspace_memberships" in statements[2]
    db.commit.assert_not_awaited()


async def test_explicit_default_rejects_concurrently_removed_membership():
    db = AsyncMock()
    db.execute.side_effect = [result(), result()]
    with pytest.raises(ValueError, match="no longer exists"):
        await select_default_membership(db, user_id=1, workspace_id=uuid.uuid4())
    assert db.execute.await_count == 2


@pytest.mark.parametrize("flags", [(True, True), (False, False), (False, True)])
async def test_list_exposes_one_effective_default_without_repair(flags):
    rows = []
    for index, flag in enumerate(flags):
        m = membership(default=flag)
        w = Workspace(
            id=m.workspace_id,
            name=f"Brand {index}",
            slug=f"brand-{index}",
            settings={},
            autonomy_mandate={},
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        rows.append((m, w))
    db = AsyncMock()
    db.execute.return_value = result(rows=rows)
    response = await list_workspaces(User(id=1), db)
    assert [r.is_default for r in response] == (
        [False, True] if flags[1] and not flags[0] else [True, False]
    )
    assert tuple(m.is_default for m, _ in rows) == flags
    db.commit.assert_not_awaited()


async def test_me_uses_same_active_deterministic_fallback():
    m = membership()
    db = AsyncMock()
    db.execute.return_value = result(m)
    user = User(id=1, email="local@example.test", is_active=True, created_at=datetime.now(UTC))
    response = await get_me(user, db)
    assert response["default_workspace_id"] == str(m.workspace_id)
    sql = str(db.execute.call_args.args[0])
    assert "workspaces.is_active IS true" in sql
    assert "is_default DESC" in sql
    assert "created_at ASC" in sql
    assert "workspace_memberships.id ASC" in sql
