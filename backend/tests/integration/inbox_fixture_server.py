"""Local-only, no-delivery HTTP fixture for inbox verification.

Run with the disposable PostgreSQL container documented in docs/inbox-verification.md.
This is not an application entry point. It starts no workers and blocks all writes
except snapshot read acknowledgments and the read-only search route. It creates
tables only in tribunal_inbox_test.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Enum, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api.v1.conversations import router
from app.db.base import Base
from app.db.session import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from tests.integration.test_inbox_postgres import (
    OTHER_WORKSPACE,
    STAMP,
    WORKSPACE,
    inbox_test_database_url,
    thread,
)

engine = create_async_engine(inbox_test_database_url())
Session = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The real ORM schema, except unrelated vector tables and ancillary FKs.
    # This verifies queries, not migrations or referential-integrity migrations.
    async with engine.begin() as connection:
        for table in Base.metadata.tables.values():
            if any(str(column.type).startswith("VECTOR") for column in table.columns):
                continue
            for column in table.columns:
                if isinstance(column.type, Enum):
                    await connection.run_sync(
                        lambda conn, enum=column.type: enum.create(conn, checkfirst=True)
                    )
            await connection.execute(
                CreateTable(table, include_foreign_key_constraints=[], if_not_exists=True)
            )
    async with Session() as db:
        if await db.scalar(select(Workspace.id).where(Workspace.id == WORKSPACE)) is None:
            db.add_all(
                [
                    Workspace(id=WORKSPACE, name="Inbox fixture", slug="inbox-fixture"),
                    Workspace(id=OTHER_WORKSPACE, name="Other fixture", slug="other-fixture"),
                    User(id=1, email="operator@example.test", hashed_password="unused-fixture"),
                    WorkspaceMembership(user_id=1, workspace_id=WORKSPACE, role="owner"),
                    Contact(
                        id=1,
                        workspace_id=WORKSPACE,
                        first_name="Fixture",
                        last_name="Lead",
                        phone_number="+15550000121",
                        lead_score=95,
                    ),
                ]
            )
            db.add_all([thread(i, contact_id=1 if i == 121 else None) for i in range(1, 123)])
            db.add(thread(200, workspace_id=OTHER_WORKSPACE))
            await db.flush()
            db.add(
                Message(
                    conversation_id=thread(121).id,
                    direction="inbound",
                    channel="sms",
                    body="Fixture only: please send appointment times.",
                    status="received",
                    created_at=STAMP,
                )
            )
            await db.commit()
        # Explicit fixture IDs must not collide with subsequent ORM inserts in
        # the existing Today integration suite. This database is disposable.
        for table in ("users", "contacts"):
            await db.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"GREATEST((SELECT COALESCE(MAX(id), 1) FROM {table}), "
                    f"(SELECT last_value FROM {table}_id_seq)), true)"
                )
            )
        await db.commit()
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api/v1/workspaces/{workspace_id}/conversations")


async def fixture_session() -> AsyncIterator[AsyncSession]:
    async with Session() as db:
        yield db


app.dependency_overrides[get_db] = fixture_session


@app.middleware("http")
async def no_delivery(request: Request, call_next):
    if request.method != "GET" and not (
        request.method == "POST" and request.url.path.endswith(("/read", "/inbox/search"))
    ):
        return JSONResponse(
            {"detail": "Fixture server disables delivery and configuration writes"}, status_code=403
        )
    return await call_next(request)


@app.get("/readyz")
async def ready():
    async with Session() as db:
        await db.execute(select(Conversation.id).limit(1))
    return {"status": "ok", "fixture": True, "delivery_disabled": True}
