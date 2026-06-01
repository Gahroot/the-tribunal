"""Tests for contact import upload orchestration."""

import io
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile

from app.models.contact import Contact
from app.services.contacts.contact_import import ContactImportService
from app.services.contacts.exceptions import ContactValidationError


def _upload(filename: str, content: bytes) -> UploadFile:
    """Build an in-memory FastAPI UploadFile."""
    return UploadFile(file=io.BytesIO(content), filename=filename)


class TestContactImportUploads:
    """CSV preview/import behavior that used to live in the contacts router."""

    async def test_preview_upload_returns_api_shape(self) -> None:
        """Preview validates filenames and includes contact field metadata."""
        service = ContactImportService(AsyncMock())
        preview = await service.preview_upload(
            _upload("contacts.csv", b"First Name,Phone,Email\nAlice,4155551234,a@example.com\n")
        )

        assert preview["headers"] == ["First Name", "Phone", "Email"]
        assert preview["sample_rows"] == [
            {"First Name": "Alice", "Phone": "4155551234", "Email": "a@example.com"}
        ]
        assert preview["suggested_mapping"] == {
            "First Name": "first_name",
            "Phone": "phone_number",
            "Email": "email",
        }
        assert {field["name"] for field in preview["contact_fields"]} >= {
            "first_name",
            "phone_number",
        }

    async def test_preview_upload_rejects_non_csv_filename(self) -> None:
        """The service owns upload filename validation."""
        service = ContactImportService(AsyncMock())

        with pytest.raises(ContactValidationError, match="File must be a CSV file"):
            await service.preview_upload(_upload("contacts.txt", b"first_name,phone_number\n"))

    async def test_import_upload_parses_mapping_and_creates_contacts(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Import upload validates form values and passes explicit column mappings through."""
        workspace_id = uuid.uuid4()
        service = ContactImportService(AsyncMock())
        captured: dict[str, object] = {}
        created = Contact(
            id=1,
            workspace_id=workspace_id,
            first_name="Alice",
            phone_number="+14155551234",
            status="qualified",
        )

        async def fake_import_csv_result(**kwargs: object):
            from app.services.contacts.contact_import import ImportResult

            captured.update(kwargs)
            return ImportResult(total_rows=1, successful=1, created_contacts=[created])

        monkeypatch.setattr(service, "import_csv", fake_import_csv_result)

        result = await service.import_upload(
            workspace_id=workspace_id,
            file=_upload("contacts.csv", b"Given,Mobile\nAlice,4155551234\n"),
            skip_duplicates=False,
            default_status="qualified",
            source="manual_upload",
            column_mapping='{"Given":"first_name","Mobile":"phone_number"}',
        )

        assert result.total_rows == 1
        assert result.successful == 1
        assert result.created_contacts == [created]
        assert captured["workspace_id"] == workspace_id
        assert captured["file_content"] == b"Given,Mobile\nAlice,4155551234\n"
        assert captured["skip_duplicates"] is False
        assert captured["default_status"] == "qualified"
        assert captured["source"] == "manual_upload"
        assert captured["explicit_mapping"] == {
            "Given": "first_name",
            "Mobile": "phone_number",
        }

    async def test_import_upload_rejects_invalid_form_values(self) -> None:
        """Invalid status and mapping JSON are reported as validation errors."""
        service = ContactImportService(AsyncMock())

        with pytest.raises(ContactValidationError, match="Invalid status"):
            await service.import_upload(
                workspace_id=uuid.uuid4(),
                file=_upload("contacts.csv", b"first_name,phone_number\n"),
                default_status="bad",
            )

        with pytest.raises(ContactValidationError, match="Invalid column_mapping JSON"):
            await service.import_upload(
                workspace_id=uuid.uuid4(),
                file=_upload("contacts.csv", b"first_name,phone_number\n"),
                column_mapping="not-json",
            )
