"""Transaction-boundary expectations for tag data access."""

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.tag import Tag
from app.services.tags.tag_repository import (
    bulk_add_tags,
    bulk_remove_tags,
    create_tag,
    delete_tag,
    update_tag,
)


class _RowsResult:
    def __init__(self, rows: list[tuple[object, ...]], scalar: int | None = None) -> None:
        self._rows = rows
        self._scalar = scalar

    def all(self) -> list[tuple[object, ...]]:
        return self._rows

    def scalar(self) -> int | None:
        return self._scalar


async def test_create_tag_flushes_without_committing() -> None:
    """Tag creation materializes rows but leaves commit ownership to the caller."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    workspace_id = uuid.uuid4()

    tag = await create_tag(
        workspace_id=workspace_id,
        name="vip",
        color="#123456",
        db=db,
    )

    assert tag.workspace_id == workspace_id
    assert tag.name == "vip"
    db.add.assert_called_once_with(tag)
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(tag)
    db.commit.assert_not_awaited()


async def test_update_tag_flushes_without_committing() -> None:
    """Tag updates stay inside the caller-owned transaction."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    tag = Tag(id=uuid.uuid4(), workspace_id=uuid.uuid4(), name="old", color="#123456")

    result = await update_tag(tag, db, {"name": "new", "color": "#654321"})

    assert result is tag
    assert tag.name == "new"
    assert tag.color == "#654321"
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(tag)
    db.commit.assert_not_awaited()


async def test_delete_tag_flushes_without_committing() -> None:
    """Tag deletion is flushed for response correctness but not committed by the repository."""
    db = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    tag = Tag(id=uuid.uuid4(), workspace_id=uuid.uuid4(), name="stale", color="#123456")

    await delete_tag(tag, db)

    db.delete.assert_awaited_once_with(tag)
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_bulk_add_tags_flushes_new_links_without_committing() -> None:
    """Bulk tag application does not commit partial ownership from inside the repository."""
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _RowsResult([(1,), (2,)]),
            _RowsResult([(uuid.UUID("00000000-0000-0000-0000-000000000001"),)]),
            _RowsResult([]),
        ]
    )
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    tag_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    created = await bulk_add_tags(
        contact_ids=[1, 2],
        tag_ids=[tag_id],
        workspace_id=uuid.uuid4(),
        db=db,
    )

    assert created == 2
    assert db.add.call_count == 2
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_bulk_remove_tags_flushes_delete_without_committing() -> None:
    """Bulk tag removal leaves the final commit to the caller-owned transaction."""
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _RowsResult([(1,), (2,)]),
            _RowsResult([], scalar=2),
            _RowsResult([]),
        ]
    )
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    removed = await bulk_remove_tags(
        contact_ids=[1, 2],
        tag_ids=[uuid.uuid4()],
        workspace_id=uuid.uuid4(),
        db=db,
    )

    assert removed == 2
    assert db.execute.await_count == 3
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
