"""Tests for bulk contact service delegation."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.contacts.bulk_service import ContactBulkService
from app.services.contacts.exceptions import ContactValidationError


class TestContactBulkService:
    """Bulk delete/update behavior extracted from ContactService."""

    async def test_bulk_delete_returns_deleted_and_error_counts(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace_id = uuid.uuid4()
        captured: dict[str, object] = {}

        async def fake_bulk_delete_contacts(**kwargs: object) -> tuple[int, list[str]]:
            captured.update(kwargs)
            return 2, ["Contact 9 not found"]

        monkeypatch.setattr(
            "app.services.contacts.bulk_service.repo_bulk_delete_contacts",
            fake_bulk_delete_contacts,
        )

        result = await ContactBulkService(AsyncMock()).bulk_delete_contacts(
            [1, 2, 9],
            workspace_id,
        )

        assert result == {
            "deleted": 2,
            "failed": 1,
            "errors": ["Contact 9 not found"],
        }
        assert captured["contact_ids"] == [1, 2, 9]
        assert captured["workspace_id"] == workspace_id

    async def test_bulk_update_status_returns_updated_and_error_counts(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace_id = uuid.uuid4()
        captured: dict[str, object] = {}

        async def fake_bulk_update_status(**kwargs: object) -> tuple[int, list[str]]:
            captured.update(kwargs)
            return 1, ["Contact 4 not found"]

        monkeypatch.setattr(
            "app.services.contacts.bulk_service.repo_bulk_update_status",
            fake_bulk_update_status,
        )

        result = await ContactBulkService(AsyncMock()).bulk_update_status(
            [3, 4],
            workspace_id,
            "qualified",
        )

        assert result == {
            "updated": 1,
            "failed": 1,
            "errors": ["Contact 4 not found"],
        }
        assert captured["contact_ids"] == [3, 4]
        assert captured["workspace_id"] == workspace_id
        assert captured["new_status"] == "qualified"

    async def test_empty_bulk_inputs_raise_validation_error(self) -> None:
        service = ContactBulkService(AsyncMock())

        with pytest.raises(ContactValidationError, match="No contact IDs provided"):
            await service.bulk_delete_contacts([], uuid.uuid4())

        with pytest.raises(ContactValidationError, match="No contact IDs provided"):
            await service.bulk_update_status([], uuid.uuid4(), "new")
