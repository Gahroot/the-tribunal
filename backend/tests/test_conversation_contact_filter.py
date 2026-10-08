"""Contact discovery must filter before workspace pagination (RF-013)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.conversations import list_conversations
from app.services.conversations.conversation_service import ConversationService


@pytest.mark.parametrize("contact_id", [101, None])
async def test_contact_filter_is_workspace_scoped_before_pagination(contact_id: int | None) -> None:
    workspace_id = uuid.uuid4()
    result = MagicMock(items=[], total=0, page=1, page_size=100, pages=0)
    with patch(
        "app.services.conversations.conversation_service.paginate",
        new=AsyncMock(return_value=result),
    ) as paginate:
        response = await ConversationService(AsyncMock()).list_conversations(
            workspace_id, page_size=100, contact_id=contact_id
        )
    statement = paginate.call_args.args[1].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "conversations.workspace_id =" in sql
    assert workspace_id in statement.params.values()
    assert ("conversations.contact_id =" in sql) is (contact_id is not None)
    if contact_id is not None:
        assert contact_id in statement.params.values()
    assert "last_message_at DESC NULLS LAST" in sql
    assert paginate.call_args.kwargs == {"page": 1, "page_size": 100}
    assert response.items == [] and response.total == 0


async def test_route_passes_contact_filter_to_service() -> None:
    workspace_id = uuid.uuid4()
    with patch("app.api.v1.conversations.ConversationService") as service:
        service.return_value.list_conversations = AsyncMock()
        await list_conversations(
            workspace_id=workspace_id,
            current_user=MagicMock(),
            db=AsyncMock(),
            workspace=MagicMock(id=workspace_id),
            page=1,
            page_size=100,
            contact_id=101,
        )
    service.return_value.list_conversations.assert_awaited_once_with(
        workspace_id=workspace_id,
        page=1,
        page_size=100,
        status_filter=None,
        channel_filter=None,
        unread_only=False,
        contact_id=101,
    )
