"""Import regressions using the real route and isolated in-memory fixtures."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.api.v1.find_leads_ai import router
from app.models.contact import Contact
from app.schemas.find_leads_ai import AIImportLeadsRequest

WORKSPACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
IMPORT_URL = f"/api/v1/workspaces/{WORKSPACE_ID}/find-leads-ai/import"


def lead(name: str, phone: str | None, website: str | None = "https://example.com") -> dict:
    return {"place_id": name, "name": name, "phone_number": phone, "website": website}


def make_import_app(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, MagicMock, AsyncMock]:
    """No database connection or real provider calls, also reusable for HTTP replay."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/workspaces/{workspace_id}/find-leads-ai")
    db = MagicMock()
    db.execute = AsyncMock(return_value=[("+14155552671",)])
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    workspace = MagicMock(id=WORKSPACE_ID)

    async def fake_user() -> MagicMock:
        return MagicMock(id=1, is_active=True)

    async def fake_db() -> MagicMock:
        return db

    async def fake_workspace(workspace_id: uuid.UUID) -> MagicMock:
        assert workspace_id == WORKSPACE_ID
        return workspace

    app.dependency_overrides[deps.get_current_user] = fake_user
    app.dependency_overrides[deps.get_db] = fake_db
    app.dependency_overrides[deps.get_workspace] = fake_workspace
    enrich = AsyncMock(side_effect=AssertionError("Unexpected enrichment provider call"))
    monkeypatch.setattr("app.api.v1.find_leads_ai.enrich_contact_data", enrich)
    tags = MagicMock()
    tags.add_tags_to_contact = AsyncMock()
    monkeypatch.setattr("app.api.v1.find_leads_ai.TagService", lambda _: tags)
    return app, db, enrich


async def test_enrichment_off_imports_unscored_at_default_80(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, db, enrich = make_import_app(monkeypatch)
    request = {
        "enable_enrichment": False,
        "leads": [
            lead("Eligible", "+14155552672"),
            lead("No website", "+14155552673", None),
            lead("Existing duplicate", "+14155552671"),
            lead("Batch duplicate", "415-555-2672"),
            lead("Missing phone", None),
            lead("Invalid phone", "invalid"),
        ],
    }
    assert AIImportLeadsRequest.model_validate(request).min_lead_score == 80
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(IMPORT_URL, json=request)
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 6
    assert result["imported"] == 2
    assert result["rejected_low_score"] == 0
    assert result["enrichment_failed"] == 0
    assert result["skipped_duplicates"] == 2
    assert result["skipped_no_phone"] == 2
    assert result["errors"] == []
    assert result["queued_for_enrichment"] == 0
    imported_details = [d for d in result["lead_details"] if d["status"] == "imported"]
    assert len(imported_details) == 2
    assert all(d["lead_score"] is None for d in imported_details)
    enrich.assert_not_called()
    contacts = [call.args[0] for call in db.add.call_args_list]
    assert len(contacts) == 2
    for contact in contacts:
        assert isinstance(contact, Contact)
        assert contact.workspace_id == WORKSPACE_ID
        assert contact.enrichment_status == "skipped"
        assert contact.enriched_at is None
        assert contact.lead_score == 0  # Existing non-null storage sentinel, not a quality score.
        assert "score_breakdown" not in contact.business_intel
        assert "google_places" in contact.business_intel
    db.commit.assert_awaited_once()
    query = db.execute.call_args.args[0]
    assert query.compile().params["workspace_id_1"] == WORKSPACE_ID


@pytest.mark.parametrize(
    ("score", "enrichment_status", "expected_status", "imported"),
    [
        (79, "enriched", "rejected_low_score", 0),
        (None, "enriched", "rejected_low_score", 0),
        (80, "enriched", "imported", 1),
        (160, "failed", "enrichment_failed", 0),
    ],
)
async def test_enabled_enrichment_preserves_threshold_and_failures(
    monkeypatch: pytest.MonkeyPatch,
    score: int | None,
    enrichment_status: str,
    expected_status: str,
    imported: int,
) -> None:
    app, db, enrich = make_import_app(monkeypatch)
    enrich.side_effect = None
    enrich.return_value = {
        "lead_score": score,
        "enrichment_status": enrichment_status,
        "business_intel": {},
        "linkedin_url": None,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(IMPORT_URL, json={"leads": [lead("Scored", "+14155552672")]})
    assert response.status_code == 200
    result = response.json()
    assert result["imported"] == imported
    assert result["lead_details"][0]["status"] == expected_status
    assert result["rejected_low_score"] == int(expected_status == "rejected_low_score")
    assert result["enrichment_failed"] == int(expected_status == "enrichment_failed")
    enrich.assert_awaited_once()
    if imported:
        assert db.add.call_args.args[0].lead_score == score
        assert db.add.call_args.args[0].enriched_at is not None
        db.commit.assert_awaited_once()
    else:
        db.add.assert_not_called()
        db.commit.assert_not_called()


async def test_enabled_without_website_still_rejects_at_80(monkeypatch: pytest.MonkeyPatch) -> None:
    app, db, enrich = make_import_app(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            IMPORT_URL, json={"leads": [lead("No website", "+14155552672", None)]}
        )
    assert response.status_code == 200
    assert response.json()["rejected_low_score"] == 1
    assert response.json()["imported"] == 0
    enrich.assert_not_called()
    db.add.assert_not_called()


async def test_enabled_provider_exception_is_not_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    app, db, enrich = make_import_app(monkeypatch)
    enrich.side_effect = RuntimeError("Fixture provider failure")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(IMPORT_URL, json={"leads": [lead("Failed", "+14155552672")]})
    assert response.status_code == 200
    assert response.json()["enrichment_failed"] == 1
    assert response.json()["imported"] == 0
    db.add.assert_not_called()
