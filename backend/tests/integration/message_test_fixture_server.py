"""Loopback RF-016 replay harness: synthetic data, no workers or outbound I/O.

Run with uvicorn on 127.0.0.1 only. Uses the same disposable database allowlist
as the inbox SQL tests. /readyz exposes IDs for the real analytics API.
"""

from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api import deps
from app.api.v1.message_tests import router as experiments_router
from app.api.webhooks import telnyx_message_handlers
from app.api.webhooks.telnyx import router as telnyx_router
from app.core.config import settings
from app.db.session import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from tests.integration.test_inbox_postgres import WORKSPACE, inbox_test_database_url
from tests.integration.test_message_test_replies import TABLES, no_external_effects, seed

schema = f"rf016_fixture_{uuid4().hex}"
engine = create_async_engine(
    inbox_test_database_url(), connect_args={"server_settings": {"search_path": schema}}
)
Session = async_sessionmaker(engine, expire_on_commit=False)
fixture_ids = {}


async def fixture_db():
    async with Session() as db:
        yield db


async def fixture_user():
    return User(id=1, email="rf016@example.invalid", full_name="Local fixture")


async def fixture_workspace():
    return Workspace(id=WORKSPACE, name="RF-016 fixture", slug="rf016-fixture")


@asynccontextmanager
async def lifespan(_app):
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        for model in (
            User,
            Workspace,
            WorkspaceMembership,
            Contact,
            Conversation,
            Message,
            *TABLES,
        ):
            await connection.execute(
                CreateTable(model.__table__, include_foreign_key_constraints=[])
            )
    async with Session() as db:
        test, _, _ = await seed(db)
        fixture_ids.update(workspace_id=str(WORKSPACE), test_id=str(test.id))
    with ExitStack() as stack:
        stack.enter_context(no_external_effects())
        stack.enter_context(patch.object(telnyx_message_handlers, "AsyncSessionLocal", Session))
        stack.enter_context(patch.object(settings, "telnyx_api_key", "fixture-no-delivery"))
        stack.enter_context(patch.object(settings, "skip_webhook_verification", True))
        stack.enter_context(
            patch(
                "app.services.approval.command_processor_service.command_processor_service.try_process_command",
                AsyncMock(return_value=False),
            )
        )
        stack.enter_context(
            patch(
                "httpx.AsyncClient.request",
                AsyncMock(side_effect=AssertionError("Fixture forbids outbound HTTP")),
            )
        )
        yield
    # Only our random fixture schema, inside the allowlisted disposable database.
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(telnyx_router, prefix="/webhooks/telnyx")
app.include_router(experiments_router, prefix="/api/v1/workspaces/{workspace_id}/message-tests")
app.dependency_overrides[get_db] = fixture_db
app.dependency_overrides[deps.get_current_user] = fixture_user
app.dependency_overrides[deps.get_workspace] = fixture_workspace


@app.middleware("http")
async def fixture_allowlist(request: Request, call_next):
    allowed = (
        request.method == "GET"
        and request.url.path == "/readyz"
        or request.method == "GET"
        and request.url.path.endswith("/analytics")
        or request.method == "POST"
        and request.url.path == "/webhooks/telnyx/sms"
    )
    if not allowed:
        return JSONResponse(status_code=405, content={"detail": "Fixture operation disabled"})
    return await call_next(request)


@app.get("/readyz")
async def ready():
    return {"fixture": True, "delivery_disabled": True, **fixture_ids}
