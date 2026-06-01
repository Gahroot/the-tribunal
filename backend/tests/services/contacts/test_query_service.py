"""Tests for contact query filter parsing and delegation."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.services.contacts.exceptions import ContactValidationError
from app.services.contacts.query_service import ContactQueryService, parse_contact_filters


class TestParseContactFilters:
    """Unit tests for route-independent contact filter parsing."""

    def test_parses_tags_and_json_filter_definition(self) -> None:
        """Comma-separated tags and JSON rules are normalized for repositories."""
        tag_one = uuid.uuid4()
        tag_two = uuid.uuid4()

        parsed = parse_contact_filters(
            tags=f" {tag_one},,{tag_two} ",
            tags_match="all",
            lead_score_min=20,
            lead_score_max=80,
            is_qualified=True,
            source="csv_import",
            company_name="Acme",
            created_after=datetime(2026, 1, 1, tzinfo=UTC),
            created_before=datetime(2026, 2, 1, tzinfo=UTC),
            enrichment_status="enriched",
            filters='{"logic":"or","rules":[{"field":"status","operator":"equals","value":"new"}]}',
        )

        assert parsed.tags == [tag_one, tag_two]
        assert parsed.tags_match == "all"
        assert parsed.lead_score_min == 20
        assert parsed.lead_score_max == 80
        assert parsed.is_qualified is True
        assert parsed.source == "csv_import"
        assert parsed.company_name == "Acme"
        assert parsed.enrichment_status == "enriched"
        assert parsed.filter_logic == "or"
        assert parsed.filter_rules == [{"field": "status", "operator": "equals", "value": "new"}]

    def test_invalid_json_raises_contact_validation_error(self) -> None:
        """Malformed filter JSON maps to a service-layer validation error."""
        with pytest.raises(ContactValidationError, match="Invalid filters JSON"):
            parse_contact_filters(filters="not-json")


class TestContactQueryService:
    """Service tests that avoid database work by patching repository calls."""

    async def test_list_contact_ids_delegates_normalized_filters(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """list_contact_ids parses route strings before calling the repository."""
        workspace_id = uuid.uuid4()
        tag_id = uuid.uuid4()
        captured: dict[str, object] = {}

        async def fake_list_contact_ids(**kwargs: object) -> tuple[list[int], int]:
            captured.update(kwargs)
            return [3, 1], 2

        monkeypatch.setattr(
            "app.services.contacts.query_service.repo_list_contact_ids",
            fake_list_contact_ids,
        )

        result = await ContactQueryService(AsyncMock()).list_contact_ids(
            workspace_id=workspace_id,
            status_filter="new",
            search="alice",
            tags=str(tag_id),
            tags_match="none",
            lead_score_min=10,
            filters='{"rules":[{"field":"source","operator":"equals","value":"form"}]}',
        )

        assert result == {"ids": [3, 1], "total": 2}
        assert captured["workspace_id"] == workspace_id
        assert captured["status_filter"] == "new"
        assert captured["search"] == "alice"
        assert captured["tags"] == [tag_id]
        assert captured["tags_match"] == "none"
        assert captured["lead_score_min"] == 10
        assert captured["filter_logic"] == "and"
        assert captured["filter_rules"] == [
            {"field": "source", "operator": "equals", "value": "form"}
        ]
