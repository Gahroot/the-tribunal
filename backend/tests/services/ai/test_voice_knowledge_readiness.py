"""RF-012: local ingestion, provider configuration and on-demand retrieval fixtures.

SQLite executes the actual readiness SQL against isolated document/chunk rows.
Provider sockets and PostgreSQL ranking rows are local fixtures; no paid calls.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.sql.dml import Delete

from app.core.config import settings
from app.models.agent import Agent
from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.elevenlabs_voice_agent import ElevenLabsVoiceAgentSession
from app.services.ai.embeddings import EmbeddingResult
from app.services.ai.grok import GrokVoiceAgentSession
from app.services.ai.live_voice_agent import LiveVoiceAgentSession
from app.services.ai.tool_executor import VoiceToolExecutor
from app.services.ai.voice_agent import VoiceAgentSession
from app.services.ai.voice_session_factory import VoiceSessionFactory
from app.services.knowledge.ingestion_service import KnowledgeIngestionService
from app.services.knowledge.knowledge_context_service import knowledge_context_service


class KnowledgeFixtureDB:
    """In-memory readiness SQL plus ingestion's small persistence surface."""

    def __init__(self, document: KnowledgeDocument) -> None:
        self.document = document
        self.chunks: list[Any] = []
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript(
            "CREATE TABLE knowledge_documents "
            "(id TEXT, workspace_id TEXT, agent_id TEXT, is_active BOOL);"
            "CREATE TABLE knowledge_chunks "
            "(id TEXT, document_id TEXT, workspace_id TEXT, agent_id TEXT);"
        )
        self.connection.execute(
            "INSERT INTO knowledge_documents VALUES (?, ?, ?, ?)",
            (document.id.hex, document.workspace_id.hex, document.agent_id.hex, document.is_active),
        )

    async def execute(self, statement: Any) -> Any:
        if isinstance(statement, Delete):
            self.chunks.clear()
            return SimpleNamespace(all=lambda: [])
        if "content_hash" in str(statement):
            return SimpleNamespace(all=lambda: [])
        compiled = statement.compile(
            dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
        )
        rows = self.connection.execute(str(compiled)).fetchall()
        ids = [uuid.UUID(row[0]) for row in rows]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ids))

    def add_all(self, chunks: list[Any]) -> None:
        self.chunks.extend(chunks)

    async def flush(self) -> None:
        for chunk in self.chunks:
            if chunk.id is None:
                chunk.id = uuid.uuid4()
                self.connection.execute(
                    "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?)",
                    (
                        chunk.id.hex,
                        chunk.document_id.hex,
                        chunk.workspace_id.hex,
                        chunk.agent_id.hex,
                    ),
                )

    def close(self) -> None:
        self.connection.close()


@pytest.fixture
def knowledge_fixture():
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="FAQ fixture",
        system_prompt="Answer business questions using reference facts.",
        enabled_tools=[],
        tool_settings={},
        voice_id="marin",
        language="en",
        calcom_event_type_id=None,
        turn_detection_mode="server_vad",
        turn_detection_threshold=0.5,
        silence_duration_ms=700,
    )
    content = (
        "# General\n"
        + ("Welcome to our business. " * 250)
        + "\n# Refund policy\nRefunds within 37 days."
    )
    document = KnowledgeDocument(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        title="Uploaded FAQ",
        content=content,
        doc_type="faq",
        is_active=True,
        token_count=len(content) // 4,
        priority=0,
    )
    db = KnowledgeFixtureDB(document)
    yield agent, document, db
    db.close()


async def local_embedder(texts: list[str]) -> EmbeddingResult:
    return EmbeddingResult(ok=True, embeddings=[[0.1] * 1536 for _ in texts])


@pytest.mark.parametrize("provider", ["openai", "grok", "elevenlabs", "live"])
@pytest.mark.parametrize(
    "state",
    [
        "ready",
        "absent",
        "unready",
        "inactive",
        "other_agent",
        "other_workspace",
        "other_chunk_agent",
        "other_chunk_workspace",
    ],
)
async def test_upload_readiness_controls_all_voice_provider_configs(
    provider: str, state: str, knowledge_fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, document, db = knowledge_fixture
    if state != "unready":
        await KnowledgeIngestionService().reindex_document(db, document, embedder=local_embedder)
    if state == "absent":
        db.connection.execute("DELETE FROM knowledge_documents")
    elif state == "inactive":
        db.connection.execute("UPDATE knowledge_documents SET is_active = 0")
    elif state in {"other_agent", "other_workspace"}:
        column = "agent_id" if state == "other_agent" else "workspace_id"
        # Fixed fixture column names, never user-supplied SQL.
        db.connection.execute(f"UPDATE knowledge_documents SET {column} = ?", (uuid.uuid4().hex,))
    elif state in {"other_chunk_agent", "other_chunk_workspace"}:
        column = "agent_id" if state == "other_chunk_agent" else "workspace_id"
        db.connection.execute(f"UPDATE knowledge_chunks SET {column} = ?", (uuid.uuid4().hex,))

    constructors = {
        "openai": lambda: VoiceAgentSession("fixture", agent),
        "grok": lambda: GrokVoiceAgentSession("fixture", agent, enable_tools=False),
        "elevenlabs": lambda: ElevenLabsVoiceAgentSession(
            "fixture", "fixture", agent, enable_tools=False
        ),
        "live": lambda: LiveVoiceAgentSession(agent),
    }
    session = constructors[provider]()
    factory = VoiceSessionFactory(settings)
    monkeypatch.setattr(
        factory, "_create_session_for_workspace", AsyncMock(return_value=(session, None))
    )
    resolved, error = await factory.create_session_for_workspace(
        db, agent.workspace_id, provider, agent
    )
    assert resolved is session and error is None
    assert agent.enabled_tools == []
    ready = state == "ready"
    assert bool(session._prompt_builder.get_knowledge_guidance()) is ready
    assert "37 days" not in session._prompt_builder.build_full_prompt()

    if provider == "openai":
        config = session._build_initial_session_config()
        names = [tool["name"] for tool in config["tools"]]
        session.ws = AsyncMock()
        await session.configure_session()
        updated = json.loads(session.ws.send.call_args.args[0])
        assert ("search_knowledge" in [t["name"] for t in updated["session"]["tools"]]) is ready
    elif provider == "live":
        prompt = session._build_start_options().prompt
        assert ("search_knowledge" in prompt) is ready
        callback = AsyncMock(return_value={"success": False})
        session.set_tool_callback(callback)
        session._submit_delegation_result = AsyncMock()
        await session._run_delegation("lookup", "search_knowledge: refund policy")
        expected_tool = "search_knowledge" if ready else "delegation"
        assert callback.call_args.args[1] == expected_tool
        return
    else:
        socket = AsyncMock()
        if provider == "grok":
            session.ws = socket
            await session._configure_session()
        else:
            session.grok_ws = socket
            await session._configure_grok_session()
        config = json.loads(socket.send.call_args.args[0])["session"]
        names = [tool.get("name") for tool in config.get("tools", [])]
    assert ("search_knowledge" in names) is ready


async def test_uploaded_fact_outside_startup_context_is_retrieved_on_demand(
    knowledge_fixture: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, document, db = knowledge_fixture
    await KnowledgeIngestionService().reindex_document(db, document, embedder=local_embedder)
    session = VoiceAgentSession("fixture", agent)
    await session.prepare_knowledge(db, agent.workspace_id)
    assert "search_knowledge" in [
        t["name"] for t in session._build_initial_session_config()["tools"]
    ]
    assert "37 days" not in session._build_initial_session_config()["instructions"]
    assert document.token_count > knowledge_context_service.PREAMBLE_TOKEN_BUDGET

    # Real retrieval pipeline with local embedding and rank-row fixtures.
    from app.services.knowledge import retrieval_service

    monkeypatch.setattr(retrieval_service, "embed_texts", local_embedder)
    hit = next(chunk for chunk in db.chunks if "37 days" in chunk.content)
    row = SimpleNamespace(
        id=hit.id,
        document_id=document.id,
        content=hit.content,
        ordinal=hit.ordinal,
        char_start=hit.char_start,
        char_end=hit.char_end,
        distance=0.01,
        rank=1.0,
    )
    retrieval_db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [row]
    title_result = MagicMock()
    title_result.all.return_value = [
        SimpleNamespace(id=document.id, title=document.title, content=document.content)
    ]
    retrieval_db.execute.side_effect = [result, result, title_result]

    @asynccontextmanager
    async def local_session():
        yield retrieval_db

    monkeypatch.setattr("app.db.session.AsyncSessionLocal", local_session)
    output = await VoiceToolExecutor(agent=agent, workspace_id=agent.workspace_id).execute(
        "search_knowledge", {"query": "refund policy"}
    )
    assert output["success"] is True
    assert output["passages"][0]["title"] == "Uploaded FAQ"
    assert "37 days" in output["passages"][0]["content"]
    # GPT-Live's existing handoff channel must reach that same read-only tool.
    live = LiveVoiceAgentSession(agent)
    await live.prepare_knowledge(db, agent.workspace_id)
    callback = AsyncMock(return_value=output)
    live.set_tool_callback(callback)
    live._submit_delegation_result = AsyncMock()
    await live._run_delegation("lookup", "search_knowledge: refund policy")
    callback.assert_awaited_once_with("lookup", "search_knowledge", {"query": "refund policy"})
    assert "37 days" in live._submit_delegation_result.call_args.args[1]
    channel = MagicMock()
    channel.readyState = "open"
    live._channel = channel
    live._pc = object()
    await live.inject_context(contact_info={"first_name": "Fixture"})
    assert (
        "search_knowledge: <your focused search query>"
        in json.loads(channel.send.call_args.args[0])["session"]["prompt"]
    )
    await live.configure_session(system_prompt="Be helpful")
    assert (
        "search_knowledge: <your focused search query>"
        in json.loads(channel.send.call_args.args[0])["session"]["prompt"]
    )
    for call in retrieval_db.execute.call_args_list:
        sql = str(call.args[0])
        assert "workspace_id" in sql and "agent_id" in sql and "is_active" in sql
        values = call.args[0].compile().params.values()
        assert agent.workspace_id in values and agent.id in values
