"""Tests for SegmentService preview/count behavior.

Unit tests with a mocked AsyncSession — no real DB required. They lock in the
contract for the ``/segments/preview`` endpoint surface: the service returns a
live ``total`` derived from ``preview_segment_contacts`` without persisting
anything.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.contact import Contact
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
