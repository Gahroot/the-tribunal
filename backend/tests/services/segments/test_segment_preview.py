"""Tests for SegmentService preview/count behavior.

Unit tests with a mocked AsyncSession — no real DB required. They lock in the
contract for the ``/segments/preview`` endpoint surface: the service returns a
live ``total`` derived from ``preview_segment_contacts`` without persisting
anything.
"""

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as SchemaValidationError
from sqlalchemy.dialects import sqlite

from app.models.contact import Contact
from app.models.segment import Segment
from app.schemas.segment import (
    FilterDefinition,
    SegmentCreate,
    SegmentPreviewRequest,
    SegmentUpdate,
)
from app.services.exceptions import ValidationError
from app.services.segments.segment_repository import build_segment_contacts_query
from app.services.segments.segment_service import SegmentService


@pytest.mark.parametrize(
    "logic,extra,expected",
    [
        ("and", [], [1, 2]),
        ("and", [{"field": "source", "operator": "equals", "value": "form"}], [1]),
        ("or", [{"field": "source", "operator": "equals", "value": "import"}], [1, 2, 3]),
    ],
)
def test_membership_executes_scoped_segment_query(logic: str, extra: list, expected: list) -> None:
    workspace_id = uuid.uuid4()
    definition = {
        "logic": logic,
        "rules": [{"field": "status", "operator": "in", "value": ["new", "qualified"]}, *extra],
    }
    query = build_segment_contacts_query(workspace_id, definition).with_only_columns(Contact.id)
    sql = str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE contacts (id INTEGER, workspace_id TEXT, status TEXT, source TEXT)"
        )
        db.executemany(
            "INSERT INTO contacts VALUES (?, ?, ?, ?)",
            [
                (1, workspace_id.hex, "new", "form"),
                (2, workspace_id.hex, "qualified", "other"),
                (3, workspace_id.hex, "lost", "import"),
                (4, uuid.uuid4().hex, "new", "import"),
            ],
        )
        assert sorted(row[0] for row in db.execute(sql)) == expected


@pytest.mark.parametrize("operator,expected", [("in", []), ("not_in", [1])])
def test_empty_membership_has_explicit_sql_semantics(operator: str, expected: list) -> None:
    workspace_id = uuid.uuid4()
    definition = FilterDefinition.model_validate(
        {"rules": [{"field": "status", "operator": operator, "value": []}]}
    ).model_dump()
    query = build_segment_contacts_query(workspace_id, definition).with_only_columns(Contact.id)
    sql = str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE contacts (id INTEGER, workspace_id TEXT, status TEXT)")
        db.execute("INSERT INTO contacts VALUES (?, ?, ?)", (1, workspace_id.hex, "new"))
        assert [row[0] for row in db.execute(sql)] == expected


@pytest.mark.parametrize("operator", ["in", "not_in"])
@pytest.mark.parametrize("value", ["new", None, 5, {"status": "new"}, [["new"]], [None]])
def test_malformed_membership_rejected_in_saved_and_public_filters(
    operator: str, value: object
) -> None:
    definition = {"rules": [{"field": "status", "operator": operator, "value": value}]}
    with pytest.raises(ValidationError, match="requires a list"):
        build_segment_contacts_query(uuid.uuid4(), definition)
    for schema in (SegmentCreate, SegmentUpdate, SegmentPreviewRequest):
        with pytest.raises(SchemaValidationError, match="requires a list"):
            schema.model_validate({"name": "Test", "definition": definition})


@pytest.mark.parametrize("operator", [["in"], {"operator": "in"}])
def test_invalid_operator_is_a_schema_validation_error(operator: object) -> None:
    with pytest.raises(SchemaValidationError):
        SegmentPreviewRequest.model_validate(
            {"definition": {"rules": [{"field": "status", "operator": operator, "value": ["new"]}]}}
        )


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
