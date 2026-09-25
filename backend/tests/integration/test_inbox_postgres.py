"""PostgreSQL regression suite: see docs/inbox-verification.md.

Runs against a disposable, loopback-only tribunal_inbox_test database, never the
configured application database. Uses the repository's integration marker; run
with -m integration when the disposable PostgreSQL service is available.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api.v1.conversations import router
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus, Message
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.conversations.conversation_service import ConversationService
from app.services.dashboard.today_queue_service import TodayQueueService

pytestmark = pytest.mark.integration

TEST_URL = "postgresql+asyncpg://tribunal_inbox_test@127.0.0.1:55432/tribunal_inbox_test"
WORKSPACE = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_WORKSPACE = uuid.UUID("22222222-2222-4222-8222-222222222222")
STAMP = datetime(2026, 9, 24, 12, tzinfo=UTC)


def inbox_test_database_url() -> str:
    value = os.environ.get("INBOX_TEST_DATABASE_URL", TEST_URL)
    parsed = make_url(value)
    if (
        parsed.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed.database != "tribunal_inbox_test"
    ):
        raise RuntimeError("Inbox checks require loopback database tribunal_inbox_test")
    return value


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Real mapped columns, isolated schema; unrelated FKs omitted, never production DDL."""
    schema = f"inbox_check_{uuid.uuid4().hex}"
    admin = create_async_engine(inbox_test_database_url())
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        inbox_test_database_url(), connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as connection:
            for model in (User, Workspace, WorkspaceMembership, Contact, Conversation, Message):
                # Ancillary CRM tables are intentionally absent. Keep all real column
                # types/defaults/uniqueness; only omit foreign keys to those tables.
                await connection.execute(
                    CreateTable(model.__table__, include_foreign_key_constraints=[])
                )
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add_all(
                [
                    User(id=1, email="operator@example.test", hashed_password="unused-fixture"),
                    Workspace(id=WORKSPACE, name="Inbox fixture", slug="inbox-fixture"),
                    Workspace(id=OTHER_WORKSPACE, name="Other fixture", slug="other-fixture"),
                    WorkspaceMembership(user_id=1, workspace_id=WORKSPACE, role="owner"),
                ]
            )
            await session.commit()
            yield session
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def thread(index: int, **changes: object) -> Conversation:
    values: dict[str, object] = {
        "id": uuid.UUID(int=index),
        "workspace_id": WORKSPACE,
        "workspace_phone": "+15550000000",
        "contact_phone": f"+1555{index:07d}",
        "ai_enabled": False,
        "ai_paused": False,
        "last_message_direction": "inbound",
        "last_message_at": STAMP,
        "unread_count": 1,
        "last_message_preview": f"Fixture message {index}",
        "status": ConversationStatus.ACTIVE,
    }
    values.update(changes)
    return Conversation(**values)


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/workspaces/{workspace_id}/conversations")

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = session_override
    # Only the session is substituted. JWT and workspace membership checks are real.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        http.headers["Authorization"] = f"Bearer {create_access_token({'sub': '1'})}"
        yield http


@pytest.mark.asyncio
async def test_pagination_search_counts_and_read_purity(db: AsyncSession) -> None:
    contacts = [
        Contact(
            id=1,
            workspace_id=WORKSPACE,
            first_name="Target",
            phone_number="+15550000121",
            last_name="Beyond",
            lead_score=95,
            email="target@example.test",
        ),
        Contact(
            id=2,
            workspace_id=OTHER_WORKSPACE,
            first_name="Secret",
            phone_number="+15550000200",
            lead_score=99,
        ),
    ]
    db.add_all(contacts)
    db.add_all([thread(i, contact_id=1 if i == 121 else None) for i in range(1, 122)])
    db.add(thread(200, workspace_id=OTHER_WORKSPACE, contact_id=2))
    # Intentionally inconsistent contact FK proves joins are scoped independently.
    db.add(thread(201, contact_id=2, last_message_preview="100%_literal"))
    await db.commit()
    service = ConversationService(db)
    with patch.object(
        db, "commit", new=AsyncMock(side_effect=AssertionError("read committed state"))
    ):
        first = await service.list_inbox(WORKSPACE, page_size=50)
        third = await service.list_inbox(WORKSPACE, page=3, page_size=50)
        assert first.total == 122 and first.pages == 3
        assert len(first.items) == 50 and len(third.items) == 22
        assert not ({x.id for x in first.items} & {x.id for x in third.items})
        assert first.counts.hot == 1 and first.counts.waiting == 122
        result = await service.list_inbox(WORKSPACE, q="Target Beyond")
        assert [x.id for x in result.items] == [uuid.UUID(int=121)]
        assert result.counts.model_dump() == {"all": 1, "waiting": 1, "hot": 1}
        assert result.items[0].contact and result.items[0].contact.first_name == "Target"
        assert (await service.list_inbox(WORKSPACE, q="TARGET@EXAMPLE.TEST")).total == 1
        assert (await service.list_inbox(WORKSPACE, q="%_")).total == 1
        assert (await service.list_inbox(WORKSPACE, q="Secret")).total == 0
        detail = await service.get_inbox_conversation(uuid.UUID(int=201), WORKSPACE)
        assert detail.contact is None and detail.unread_count == 1 and not detail.ai_enabled
    assert not db.dirty and not db.new


@pytest.mark.asyncio
async def test_shared_waiting_definition_and_read_race(db: AsyncSession) -> None:
    rows = [
        thread(1),
        thread(2, unread_count=0),
        thread(3, ai_enabled=True, ai_paused=True),
        thread(4, ai_enabled=True),
        thread(5, last_message_direction="outbound"),
        thread(6, status=ConversationStatus.BLOCKED),
        thread(7, status=ConversationStatus.ARCHIVED),
    ]
    db.add_all(rows)
    await db.commit()
    service = ConversationService(db)
    waiting = await service.list_inbox(WORKSPACE, view="waiting")
    assert [x.id for x in waiting.items] == [x.id for x in rows[:3]]
    today = await TodayQueueService(db)._replies_waiting_item(WORKSPACE)
    assert today and today.count == waiting.total == 3
    assert today.href == "/conversations?view=waiting"
    assert set(today.payload["conversation_ids"]) == {str(x.id) for x in rows[:3]}
    snapshot = waiting.items[0]
    assert (
        await service.mark_read(snapshot.id, WORKSPACE, snapshot.last_message_at, 1)
    ).marked_read
    assert (await service.list_inbox(WORKSPACE, view="waiting")).total == 3
    await db.execute(
        update(Conversation)
        .where(Conversation.id == snapshot.id)
        .values(unread_count=2, last_message_at=STAMP + timedelta(seconds=1))
    )
    await db.commit()
    assert not (
        await service.mark_read(snapshot.id, WORKSPACE, snapshot.last_message_at, 1)
    ).marked_read
    db.expire_all()
    assert (await service.get_inbox_conversation(snapshot.id, WORKSPACE)).unread_count == 2
    await db.execute(
        update(Conversation)
        .where(Conversation.id.in_([uuid.UUID(int=1), uuid.UUID(int=3)]))
        .values(last_message_direction="outbound")
    )
    await db.commit()
    item = await TodayQueueService(db)._replies_waiting_item(WORKSPACE)
    assert item and item.href == f"/conversations?view=waiting&conversation={uuid.UUID(int=2)}"


@pytest.mark.asyncio
async def test_http_auth_scope_validation_and_recent_messages(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    own, other = thread(1), thread(2, workspace_id=OTHER_WORKSPACE)
    db.add_all([own, other])
    await db.flush()
    db.add_all(
        [
            Message(
                conversation_id=own.id,
                direction="inbound",
                channel="sms",
                body=f"Message {i}",
                status="received",
                created_at=STAMP + timedelta(seconds=i),
            )
            for i in range(105)
        ]
    )
    await db.commit()
    root = f"/api/v1/workspaces/{WORKSPACE}/conversations"
    for path in ("/inbox", f"/{own.id}/inbox-detail", f"/{own.id}/messages"):
        response = await client.get(root + path)
        assert response.status_code == 200, response.text
    messages = (await client.get(root + f"/{own.id}/messages")).json()
    assert (
        len(messages) == 100
        and messages[0]["body"] == "Message 5"
        and messages[-1]["body"] == "Message 104"
    )
    searched = await client.post(
        root + "/inbox/search", json={"q": "Fixture message 1", "view": "waiting"}
    )
    assert searched.status_code == 200
    assert [item["id"] for item in searched.json()["items"]] == [str(own.id)]
    assert (await client.post(root + "/inbox/search", json={"q": "x" * 201})).status_code == 422
    assert (
        await client.post(
            f"/api/v1/workspaces/{OTHER_WORKSPACE}/conversations/inbox/search", json={}
        )
    ).status_code == 404
    assert (await client.get(root + "/inbox?view=unknown")).status_code == 422
    for suffix in ("page=0", "page_size=101", "q=" + "x" * 201):
        assert (await client.get(root + "/inbox?" + suffix)).status_code == 422
    for path in (f"/{other.id}/inbox-detail", f"/{other.id}/messages"):
        assert (await client.get(root + path)).status_code == 404
    assert (
        await client.post(
            root + f"/{other.id}/read", json={"last_message_at": None, "unread_count": 1}
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/workspaces/{OTHER_WORKSPACE}/conversations/inbox")
    ).status_code == 404
    response = await client.post(
        root + f"/{own.id}/read", json={"last_message_at": STAMP.isoformat(), "unread_count": 1}
    )
    assert response.status_code == 200 and response.json()["marked_read"] is True
    client.headers.pop("Authorization")
    assert (await client.get(root + "/inbox")).status_code == 401
    assert (await client.post(root + "/inbox/search", json={})).status_code == 401


@pytest.mark.asyncio
async def test_empty_search_nulls_and_message_bounds(db: AsyncSession) -> None:
    service = ConversationService(db)
    assert (await service.list_inbox(WORKSPACE)).model_dump()["counts"] == {
        "all": 0,
        "hot": 0,
        "waiting": 0,
    }
    db.add_all([thread(1, last_message_at=None), thread(2), thread(3)])
    await db.commit()
    for view in ("all", "waiting"):
        result = await service.list_inbox(WORKSPACE, view=view)
        assert [x.id for x in result.items] == [uuid.UUID(int=i) for i in (2, 3, 1)]
    assert (await service.list_inbox(WORKSPACE, page=20)).items == []
    assert (await service.list_inbox(WORKSPACE, q="missing")).total == 0
    assert (await service.list_inbox(WORKSPACE, q="+1 (555) 000-0002")).total == 1


@pytest.mark.asyncio
async def test_empty_thread_has_boolean_reply_state(db: AsyncSession) -> None:
    db.add(thread(1, last_message_direction=None, last_message_at=None, unread_count=0))
    await db.commit()
    service = ConversationService(db)
    result = await service.list_inbox(WORKSPACE)
    assert result.items[0].needs_human_reply is False
    assert result.counts.waiting == 0
    assert (
        await service.get_inbox_conversation(uuid.UUID(int=1), WORKSPACE)
    ).needs_human_reply is False


@pytest.mark.asyncio
async def test_read_snapshot_requires_timezone(db: AsyncSession, client: httpx.AsyncClient) -> None:
    db.add(thread(1))
    await db.commit()
    response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE}/conversations/{uuid.UUID(int=1)}/read",
        json={"last_message_at": "2026-09-24T12:00:00", "unread_count": 1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_call_metadata_is_preserved(db: AsyncSession, client: httpx.AsyncClient) -> None:
    db.add(thread(1))
    await db.flush()
    db.add(
        Message(
            conversation_id=uuid.UUID(int=1),
            direction="inbound",
            channel="voice",
            body="Call summary",
            transcript="Fixture call transcript",
            duration_seconds=45,
            recording_url="https://example.test/fixture.wav",
            status="received",
        )
    )
    await db.commit()
    response = await client.get(
        f"/api/v1/workspaces/{WORKSPACE}/conversations/{uuid.UUID(int=1)}/messages"
    )
    assert response.status_code == 200
    message = response.json()[0]
    assert (message["transcript"], message["duration_seconds"], message["recording_url"]) == (
        "Fixture call transcript",
        45,
        "https://example.test/fixture.wav",
    )
