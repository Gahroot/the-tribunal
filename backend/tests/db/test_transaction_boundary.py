"""Tests for backend transaction-boundary helpers."""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import transaction_boundary


class _FakeSession:
    def __init__(self, *, active: bool = True, commit_error: Exception | None = None) -> None:
        self.active = active
        self.commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0

    def in_transaction(self) -> bool:
        return self.active

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error
        self.active = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.active = False


async def test_transaction_boundary_commits_open_transaction_on_success() -> None:
    """Successful units of work commit exactly once at the boundary."""
    session = _FakeSession(active=True)

    async with transaction_boundary(cast(AsyncSession, session)):
        assert session.in_transaction()

    assert session.commits == 1
    assert session.rollbacks == 0
    assert not session.in_transaction()


async def test_transaction_boundary_skips_commit_without_open_transaction() -> None:
    """Read-only units of work do not commit when no transaction was opened."""
    session = _FakeSession(active=False)

    async with transaction_boundary(cast(AsyncSession, session)):
        assert not session.in_transaction()

    assert session.commits == 0
    assert session.rollbacks == 0


async def test_transaction_boundary_rolls_back_open_transaction_on_error() -> None:
    """Exceptions inside the unit of work roll back before propagating."""
    session = _FakeSession(active=True)

    with pytest.raises(RuntimeError, match="boom"):
        async with transaction_boundary(cast(AsyncSession, session)):
            raise RuntimeError("boom")

    assert session.commits == 0
    assert session.rollbacks == 1
    assert not session.in_transaction()


async def test_transaction_boundary_rolls_back_when_commit_fails() -> None:
    """Commit failures roll back the still-open transaction before propagating."""
    session = _FakeSession(active=True, commit_error=RuntimeError("commit failed"))

    with pytest.raises(RuntimeError, match="commit failed"):
        async with transaction_boundary(cast(AsyncSession, session)):
            assert session.in_transaction()

    assert session.commits == 1
    assert session.rollbacks == 1
    assert not session.in_transaction()
