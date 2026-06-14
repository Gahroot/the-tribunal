"""Tests for SegmentService preview/count behavior.

Unit tests with a mocked AsyncSession — no real DB required. They lock in the
contract for the ``/segments/preview`` endpoint surface: the service returns a
live ``total`` derived from ``preview_segment_contacts`` without persisting
anything.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.contact import Contact
from app.models.segment import Segment
from app.services.segments.segment_service import SegmentService


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_preview_segment_returns_live_total(mock_db: AsyncMock) -> None:
    """preview_segment surfaces the count from preview_segment_contacts."""
    workspace_id = uuid.uuid4()
    definition = {
        "logic": "and",
        "rules": [{"field": "status", "operator": "equals", "value": "new"}],
    }
    sample = [Contact(), Contact()]

    service = SegmentService(mock_db)
    with patch(
        "app.services.segments.segment_service.preview_segment_contacts",
        new=AsyncMock(return_value=(sample, 42)),
    ) as preview_fn:
        result = await service.preview_segment(workspace_id, definition)

    assert result == {"total": 42}
    preview_fn.assert_awaited_once()
    # The definition is passed straight through to the repository helper.
    args, _kwargs = preview_fn.call_args
    assert args[0] == workspace_id
    assert args[1] == definition
    # Preview is read-only: it must not commit/persist.
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_preview_segment_handles_empty_match(mock_db: AsyncMock) -> None:
    """A definition that matches nothing returns total=0."""
    service = SegmentService(mock_db)
    with patch(
        "app.services.segments.segment_service.preview_segment_contacts",
        new=AsyncMock(return_value=([], 0)),
    ):
        result = await service.preview_segment(uuid.uuid4(), {"logic": "and", "rules": []})

    assert result == {"total": 0}


@pytest.mark.asyncio
async def test_create_segment_computes_contact_count_before_persisting(
    mock_db: AsyncMock,
) -> None:
    """Creating a segment stores the same live count shown by preview."""
    workspace_id = uuid.uuid4()
    segment_id = uuid.uuid4()
    definition = {
        "logic": "and",
        "rules": [{"field": "status", "operator": "equals", "value": "new"}],
    }
    created_at = datetime.now(UTC)

    async def fake_create_segment(**kwargs: Any) -> Segment:
        return Segment(
            id=segment_id,
            workspace_id=kwargs["workspace_id"],
            name=kwargs["name"],
            description=kwargs["description"],
            definition=kwargs["definition"],
            is_dynamic=kwargs["is_dynamic"],
            contact_count=kwargs["contact_count"],
            last_computed_at=kwargs["last_computed_at"],
            created_at=created_at,
            updated_at=created_at,
        )

    service = SegmentService(mock_db)
    with (
        patch(
            "app.services.segments.segment_service.resolve_segment_contacts",
            new=AsyncMock(return_value=([101, 202, 303], 3)),
        ) as resolve_fn,
        patch(
            "app.services.segments.segment_service.create_segment",
            new=AsyncMock(side_effect=fake_create_segment),
        ) as create_fn,
    ):
        result = await service.create_segment(
            workspace_id=workspace_id,
            name="Hot leads",
            definition=definition,
            description="Ready for follow-up",
        )

    assert result.contact_count == 3
    assert result.last_computed_at is not None

    resolve_fn.assert_awaited_once()
    segment_seed, resolve_db = resolve_fn.call_args.args
    assert segment_seed.workspace_id == workspace_id
    assert segment_seed.definition == definition
    assert resolve_db is mock_db

    create_fn.assert_awaited_once()
    create_kwargs = create_fn.call_args.kwargs
    assert create_kwargs["contact_count"] == 3
    assert create_kwargs["last_computed_at"] == result.last_computed_at
