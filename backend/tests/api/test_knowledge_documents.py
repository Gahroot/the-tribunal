"""HTTP boundaries for indexed knowledge readiness and actionable ingest failures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import knowledge_documents as routes
from app.models.knowledge_document import KnowledgeDocument
from app.services.knowledge.ingestion_service import IngestionError

WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000012")
AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000013")
DOCUMENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000014")
PATH = f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{AGENT_ID}/knowledge-documents"


def create_fixture_app() -> FastAPI:
    """Loopback probe app with local persistence fixtures, no provider clients."""
    app = FastAPI()
    app.include_router(
        routes.router,
        prefix="/api/v1/workspaces/{workspace_id}/agents/{agent_id}/knowledge-documents",
    )
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    document = KnowledgeDocument(
        id=DOCUMENT_ID,
        workspace_id=WORKSPACE_ID,
        agent_id=AGENT_ID,
        title="FAQ fixture",
        content="Refunds within 37 days.",
        doc_type="faq",
        token_count=7,
        priority=0,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    agent = SimpleNamespace(id=AGENT_ID, workspace_id=WORKSPACE_ID)

    async def execute(statement):
        sql = str(statement)
        if "FROM agents" in sql:
            return SimpleNamespace(scalar_one_or_none=lambda: agent)
        if "EXISTS" in sql:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [DOCUMENT_ID]))
        if "count(" in sql:
            return SimpleNamespace(scalar=lambda: 1)
        if "sum(" in sql:
            return SimpleNamespace(scalar_one=lambda: document.token_count)
        if "knowledge_documents.id =" in sql:
            return SimpleNamespace(scalar_one_or_none=lambda: document)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [document]))

    db.execute = AsyncMock(side_effect=execute)

    def add(new_document):
        new_document.id = DOCUMENT_ID
        new_document.created_at = document.created_at
        new_document.updated_at = document.updated_at

    db.add.side_effect = add

    async def database():
        return db

    async def user():
        return SimpleNamespace(id=1)

    async def workspace():
        return SimpleNamespace(id=WORKSPACE_ID)

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_workspace] = workspace
    app.state.db = db
    return app


@pytest.mark.parametrize("ready", [True, False])
async def test_list_serializes_indexed_readiness(ready, monkeypatch):
    app = create_fixture_app()
    monkeypatch.setattr(
        routes.knowledge_context_service,
        "get_ready_document_ids",
        AsyncMock(return_value={DOCUMENT_ID} if ready else set()),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(PATH)
    assert response.status_code == 200
    assert response.json()["items"][0]["retrieval_ready"] is ready


async def test_upload_index_failure_returns_retry_action_and_rolls_back(monkeypatch):
    app = create_fixture_app()
    monkeypatch.setattr(
        routes.knowledge_ingestion_service,
        "reindex_document",
        AsyncMock(side_effect=IngestionError("Local embedding fixture unavailable")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.post(
            PATH, json={"title": "FAQ", "content": "Refunds within 37 days."}
        )
    assert response.status_code == 502
    assert "not saved" in response.json()["detail"]
    assert "retry" in response.json()["detail"]
    app.state.db.rollback.assert_awaited_once()
    app.state.db.commit.assert_not_awaited()


async def test_upload_response_is_ready_after_indexing(monkeypatch):
    app = create_fixture_app()
    # No paid embedding request: persistence and readiness SQL remain local fixtures.
    ingest = AsyncMock(return_value=SimpleNamespace(chunk_count=1))
    monkeypatch.setattr(routes.knowledge_ingestion_service, "reindex_document", ingest)
    monkeypatch.setattr(routes, "emit_automation_event", AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.post(
            PATH, json={"title": "FAQ", "content": "Refunds within 37 days."}
        )
    assert response.status_code == 201
    assert response.json()["retrieval_ready"] is True
    ingest.assert_awaited_once()
