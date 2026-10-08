"""Auth + happy-path tests for the practice-arena (roleplay) router.

Uses dependency overrides (no real DB) and stubs ``RoleplayService`` methods so
routing, auth, and response serialization are exercised end-to-end.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import roleplay as roleplay_module

from app.services.ai.roleplay import roleplay_service as engine
from app.services.ai.roleplay.report_scorer import RehearsalReport

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_app(*, authed: bool) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)
    if authed:

        async def override_get_db() -> AsyncIterator[AsyncMock]:
            yield AsyncMock()

        async def override_get_workspace() -> MagicMock:
            return SimpleNamespace(id=WS_ID, is_active=True)

        async def override_get_current_user() -> MagicMock:
            return SimpleNamespace(id=1, is_active=True)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_workspace] = override_get_workspace
        app.dependency_overrides[get_current_user] = override_get_current_user

    app.include_router(
        roleplay_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/roleplay",
    )
    return app


def _persona() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=None,
        slug="skeptical-homeowner",
        name="Skeptical Homeowner",
        description="Guarded homeowner",
        difficulty="hard",
        channel="sms",
        persona_prompt="be skeptical",
        opening_message="Who is this?",
        objections=["distrust"],
        goal="book a visit",
        is_builtin=True,
        created_at=now,
        updated_at=now,
    )


def _run(status: str = "completed") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=WS_ID,
        agent_id=uuid.uuid4(),
        persona_id=uuid.uuid4(),
        agent_name="Closer Bot",
        persona_name="Skeptical Homeowner",
        rehearsee="ai",
        channel="sms",
        status=status,
        max_turns=6,
        transcript=[{"role": "prospect", "content": "Who is this?"}],
        scores={"tone_label": "warm"},
        overall_score=82.0,
        objection_coverage=75.0,
        booking_attempted=True,
        tone_score=80.0,
        strengths=["clear"],
        gaps=["no urgency"],
        suggestions=["add pricing"],
        summary="Good rapport.",
        error=None,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = _make_app(authed=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def noauth_client() -> AsyncIterator[AsyncClient]:
    app = _make_app(authed=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _engine_app(mp: pytest.MonkeyPatch, failure: Exception | None, fail_after: int = 0):
    """Real router + engine with persisted in-memory runs and no provider network."""
    app = _make_app(authed=True)
    runs = {}
    db = MagicMock()
    db.commit = AsyncMock()

    async def refresh(run):
        if run.id is None:
            run.id = uuid.uuid4()
            run.created_at = run.updated_at = datetime.now(UTC)
            run.scores = {}
            run.strengths = []
            run.gaps = []
            run.suggestions = []
        runs[run.id] = run

    db.refresh = AsyncMock(side_effect=refresh)
    db.execute = AsyncMock(
        side_effect=lambda stmt: SimpleNamespace(
            scalar_one_or_none=lambda: runs.get(stmt.compile().params.get("id_1"))
        )
    )

    async def get_fixture_db():
        yield db

    app.dependency_overrides[get_db] = get_fixture_db
    agent = SimpleNamespace(id=uuid.uuid4(), name="Fixture agent", temperature=0.7)
    mp.setattr(engine.RoleplayService, "_load_agent", AsyncMock(return_value=agent))
    mp.setattr(engine.RoleplayService, "get_persona", AsyncMock(return_value=_persona()))
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Real fixture reply"))]
    )
    provider = AsyncMock(return_value=response)
    if failure is not None:
        provider.side_effect = [response] * fail_after + [failure, response, response, response]
    model_client = MagicMock()
    model_client.chat.completions.create = provider
    mp.setattr(engine.RoleplayService, "_client", AsyncMock(return_value=model_client))
    mp.setattr(engine, "get_workspace_timezone", AsyncMock(return_value="UTC"))
    mp.setattr(engine, "build_agent_system_prompt", AsyncMock(return_value="Fixture prompt"))
    mp.setattr(engine, "generate_prospect_reply", AsyncMock(return_value="Tell me more"))
    mp.setattr(engine, "resolve_model", AsyncMock())
    scorer = AsyncMock(return_value=RehearsalReport(82, 75, True, 80, "Good rapport"))
    mp.setattr(engine, "score_rehearsal", scorer)
    completed = AsyncMock()
    mp.setattr(engine.RoleplayService, "_emit_completed_event", completed)
    return app, runs, provider, scorer, completed


@pytest.mark.parametrize("failure", [TimeoutError(), RuntimeError("private provider diagnostic")])
@pytest.mark.parametrize("fail_after", [0, 1])
async def test_agent_generation_failure_cannot_be_completed_or_rescored(failure, fail_after):
    with pytest.MonkeyPatch().context() as mp:
        app, runs, provider, scorer, completed = _engine_app(mp, failure, fail_after)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as ac:
            url = f"/api/v1/workspaces/{WS_ID}/roleplay/runs"
            payload = {
                "agent_id": str(uuid.uuid4()),
                "persona_id": str(uuid.uuid4()),
                "max_turns": 2,
            }
            response = await ac.post(url, json=payload)
            assert response.status_code == 201
            body = response.json()
            assert body["status"] == "failed"
            assert body["overall_score"] is None
            assert body["tone_score"] is None
            assert body["objection_coverage"] is None
            assert body["booking_attempted"] is None
            assert body["completed_at"] is None
            assert body["scores"] == {}
            assert "not evaluated" in body["error"]
            assert "retry" in body["error"]
            assert "private provider diagnostic" not in response.text
            assert len(body["transcript"]) == 1 + 2 * fail_after
            assert provider.await_count == fail_after + 1
            scorer.assert_not_awaited()
            completed.assert_not_awaited()
            assert len(runs) == 1
            persisted = await ac.get(f"{url}/{body['id']}")
            assert persisted.json() == body
            rescore = await ac.post(f"{url}/{body['id']}/score")
            assert rescore.status_code == 400
            scorer.assert_not_awaited()
            completed.assert_not_awaited()
            # A healthy later provider request must not redeem the failed run.
            recovery = await ac.post(url, json=payload)
            assert recovery.status_code == 201
            healthy = recovery.json()
            assert healthy["id"] != body["id"]
            assert healthy["status"] == "completed"
            assert healthy["overall_score"] == 82
            assert healthy["completed_at"] is not None
            assert healthy["error"] is None
            assert len(healthy["transcript"]) == 5
            scorer.assert_awaited_once()
            completed.assert_awaited_once()
            assert (await ac.get(f"{url}/{body['id']}")).json()["status"] == "failed"


class TestRoleplayAuth:
    async def test_personas_requires_auth(self, noauth_client: AsyncClient) -> None:
        resp = await noauth_client.get(f"/api/v1/workspaces/{WS_ID}/roleplay/personas")
        assert resp.status_code == 401

    async def test_create_run_requires_auth(self, noauth_client: AsyncClient) -> None:
        resp = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/roleplay/runs",
            json={"agent_id": str(uuid.uuid4()), "persona_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401


class TestRoleplayHappyPath:
    async def test_list_personas(self, client: AsyncClient) -> None:
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                roleplay_module.RoleplayService,
                "list_personas",
                AsyncMock(return_value=[_persona()]),
            )
            resp = await client.get(f"/api/v1/workspaces/{WS_ID}/roleplay/personas")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["slug"] == "skeptical-homeowner"
        assert body[0]["is_builtin"] is True
        assert body[0]["objections"] == ["distrust"]

    async def test_create_run_returns_scored_report(self, client: AsyncClient) -> None:
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                roleplay_module.RoleplayService,
                "create_run",
                AsyncMock(return_value=_run("completed")),
            )
            resp = await client.post(
                f"/api/v1/workspaces/{WS_ID}/roleplay/runs",
                json={
                    "agent_id": str(uuid.uuid4()),
                    "persona_id": str(uuid.uuid4()),
                    "rehearsee": "ai",
                    "max_turns": 6,
                },
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        assert body["overall_score"] == 82.0
        assert body["booking_attempted"] is True
        assert body["suggestions"] == ["add pricing"]
        assert body["transcript"][0]["role"] == "prospect"

    async def test_max_turns_validation(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/workspaces/{WS_ID}/roleplay/runs",
            json={
                "agent_id": str(uuid.uuid4()),
                "persona_id": str(uuid.uuid4()),
                "max_turns": 99,
            },
        )
        assert resp.status_code == 422
