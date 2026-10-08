"""Profile partial updates with real authentication and isolated SQLite persistence."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.api.v1.settings import router
from app.core.encryption import hash_phone
from app.core.security import create_access_token
from app.models.user import User

PROFILE_URL = "/api/v1/settings/users/me/profile"
SAVED_PHONE = "+12025550123"


@contextmanager
def profile_fixture_app() -> Iterator[FastAPI]:
    """Use the real user model, commits and auth, without touching a configured DB."""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    User.__table__.create(engine)
    with Session(engine) as session:
        session.add(
            User(
                id=1,
                email="profile-fixture@example.test",
                hashed_password="fixture-not-a-login-password",
                full_name="Profile Fixture",
                phone_number=SAVED_PHONE,
                avatar_url="https://example.test/avatar.png",
                timezone="America/New_York",
            )
        )
        session.commit()
        # Adapt the built-in SQLite driver to the three async methods used here.
        db = AsyncMock()
        db.execute.side_effect = session.execute
        db.commit.side_effect = session.commit
        db.refresh.side_effect = session.refresh

        async def fixture_db() -> AsyncIterator[AsyncMock]:
            yield db
            session.expunge_all()  # Next request must read committed values anew.

        app = FastAPI()
        app.dependency_overrides[get_db] = fixture_db
        app.include_router(router, prefix="/api/v1/settings")
        app.state.profile_session = session
        yield app
    engine.dispose()


@pytest.fixture
async def profile_client() -> AsyncIterator[tuple[AsyncClient, Session]]:
    with profile_fixture_app() as app:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {create_access_token({'sub': '1'})}"},
        ) as client:
            yield client, app.state.profile_session


@pytest.mark.parametrize(
    "updates, expected",
    [
        ({"phone_number": None}, None),
        ({"full_name": "Renamed Fixture"}, SAVED_PHONE),
        ({"phone_number": "+12025550124"}, "+12025550124"),
    ],
)
async def test_profile_phone_clear_omit_replace(profile_client, updates, expected):
    client, session = profile_client
    before = await client.get(PROFILE_URL)
    assert before.status_code == 200
    assert before.json()["phone_number"] == SAVED_PHONE

    response = await client.put(PROFILE_URL, json=updates)
    assert response.status_code == 200
    assert response.json()["phone_number"] == expected
    after = await client.get(PROFILE_URL)
    assert after.status_code == 200
    assert after.json() == response.json()
    for field in ("id", "email", "timezone", "avatar_url", "created_at"):
        assert after.json()[field] == before.json()[field]
    if "full_name" not in updates:
        assert after.json()["full_name"] == before.json()["full_name"]
    user = session.get(User, 1)
    assert user.phone_number == expected
    assert user.phone_hash == (hash_phone(expected) if expected else None)


@pytest.mark.parametrize("field", ["full_name", "avatar_url"])
async def test_profile_other_nullable_fields_can_be_cleared(profile_client, field):
    client, _ = profile_client
    before = (await client.get(PROFILE_URL)).json()
    assert before[field] is not None
    response = await client.put(PROFILE_URL, json={field: None})
    assert response.status_code == 200
    expected = {**before, field: None}
    assert response.json() == expected
    assert (await client.get(PROFILE_URL)).json() == expected


async def test_profile_preserves_identity_and_nonnullable_timezone(profile_client):
    client, session = profile_client
    before = (await client.get(PROFILE_URL)).json()
    response = await client.put(
        PROFILE_URL,
        json={
            "timezone": None,
            "id": 2,
            "email": "changed@example.test",
            "hashed_password": "changed",
            "is_active": False,
            "is_superuser": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == before
    assert (await client.get(PROFILE_URL)).json() == before
    user = session.get(User, 1)
    assert user.hashed_password == "fixture-not-a-login-password"
    assert user.is_active is True
    assert user.is_superuser is False


@pytest.mark.parametrize(
    "updates",
    [
        {"phone_number": {"invalid": "type"}},
        {"full_name": []},
        {"avatar_url": "x" * 1025},
    ],
)
async def test_profile_retains_input_validation(profile_client, updates):
    client, _ = profile_client
    before = (await client.get(PROFILE_URL)).json()
    response = await client.put(PROFILE_URL, json=updates)
    assert response.status_code == 422
    assert (await client.get(PROFILE_URL)).json() == before


async def test_profile_requires_authentication(profile_client):
    client, _ = profile_client
    client.headers.pop("Authorization")
    assert (await client.get(PROFILE_URL)).status_code == 401
    assert (await client.put(PROFILE_URL, json={"phone_number": None})).status_code == 401
