"""Contact import service - CSV import logic."""

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.contacts.exceptions import ContactValidationError
from app.services.tags import TagService
from app.utils.phone import normalize_phone_safe

logger = structlog.get_logger()

# Expected CSV columns and their mappings.
#
# Header matching is case-insensitive (see ``find_csv_column`` / ``preview_csv``).
# Aliases include the verbatim headers emitted by third-party exporters we
# support out of the box — notably Jobber's "Export Client Information" CSV,
# which splits the mailing address into Street1/Street2/City/State/Zip — so a
# raw export auto-maps with no manual column mapping. See ``JOBBER_CSV_PRESET``.
CSV_FIELD_MAPPING = {
    "first_name": ["first_name", "first name", "firstname", "first", "name"],
    "last_name": ["last_name", "last name", "lastname", "last", "surname"],
    "email": ["email", "email_address", "email address", "e-mail"],
    "phone_number": [
        "phone_number",
        "phone number",
        "phone",
        "mobile",
        "mobile phone",
        "cell",
        "telephone",
        "tel",
    ],
    "company_name": ["company_name", "company name", "company", "organization", "org"],
    "status": ["status", "lead_status", "lead status"],
    "tags": ["tags", "tag", "labels"],
    "notes": ["notes", "note", "comments", "comment", "description"],
    "address_line1": [
        "address_line1",
        "address line 1",
        "address",
        "street",
        "street1",
        "street 1",
        "street address",
    ],
    "address_line2": ["address_line2", "address line 2", "street2", "street 2", "unit", "suite"],
    "address_city": ["address_city", "city", "town"],
    "address_state": ["address_state", "state", "province", "state/province", "region"],
    "address_zip": [
        "address_zip",
        "zip",
        "zip code",
        "zipcode",
        "postal code",
        "postal_code",
        "zip/postal code",
    ],
}

VALID_STATUSES = {"new", "contacted", "qualified", "converted", "lost"}

# Canonical Jobber "Export Client Information" CSV → contact field mapping.
#
# Jobber exports one row per client with the mailing address split across
# Street1/Street2/City/State/Zip. Every header below is also registered as an
# alias in ``CSV_FIELD_MAPPING`` so the import preview auto-detects a raw Jobber
# export end-to-end; this dict is the explicit, documented source of truth the
# frontend can apply directly (and that ``test_contact_import`` guards against
# alias drift). Jobber columns we have no home for — Title, Country, Client
# ID/J_ID, and the per-client communication flags — are intentionally dropped.
JOBBER_CSV_PRESET: dict[str, str] = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Company Name": "company_name",
    "Email": "email",
    "Phone Number": "phone_number",
    "Street1": "address_line1",
    "Street2": "address_line2",
    "City": "address_city",
    "State": "address_state",
    "Zip Code": "address_zip",
    "Tags": "tags",
}

CONTACT_FIELDS = [
    {"name": "first_name", "label": "First Name", "required": True},
    {"name": "last_name", "label": "Last Name", "required": False},
    {"name": "email", "label": "Email", "required": False},
    {"name": "phone_number", "label": "Phone Number", "required": True},
    {"name": "company_name", "label": "Company Name", "required": False},
    {"name": "status", "label": "Status", "required": False},
    {"name": "tags", "label": "Tags", "required": False},
    {"name": "notes", "label": "Notes", "required": False},
    {"name": "address_line1", "label": "Address Line 1", "required": False},
    {"name": "address_line2", "label": "Address Line 2", "required": False},
    {"name": "address_city", "label": "City", "required": False},
    {"name": "address_state", "label": "State/Province", "required": False},
    {"name": "address_zip", "label": "Zip/Postal Code", "required": False},
]


@dataclass
class ImportErrorDetail:
    """Detail about a single import error."""

    row: int
    field: str | None = None
    error: str = ""


@dataclass
class ImportResult:
    """Result of a CSV import operation."""

    total_rows: int = 0
    successful: int = 0
    failed: int = 0
    skipped_duplicates: int = 0
    errors: list[ImportErrorDetail] = field(default_factory=list)
    created_contacts: list[Contact] = field(default_factory=list)


def find_csv_column(headers: list[str] | tuple[str, ...], field_name: str) -> str | None:
    """Find the CSV column that matches a field name.

    Args:
        headers: List of CSV header names
        field_name: Field name to find mapping for

    Returns:
        Actual header name from CSV or None
    """
    possible_names = CSV_FIELD_MAPPING.get(field_name, [field_name])
    headers_lower = [h.lower().strip() for h in headers]

    for name in possible_names:
        if name.lower() in headers_lower:
            idx = headers_lower.index(name.lower())
            return headers[idx]
    return None


def validate_email(email: str) -> bool:
    """Validate email format.

    Args:
        email: Email string to validate

    Returns:
        True if valid or empty, False otherwise
    """
    if not email:
        return True
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def clean_phone_number(phone: str) -> str | None:
    """Clean and validate phone number.

    Args:
        phone: Phone number string

    Returns:
        Normalized phone number or None if invalid
    """
    if not phone:
        return None
    # Remove common formatting characters
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if len(cleaned) < 10:
        return None
    return normalize_phone_safe(cleaned)


def _get_csv_field(
    row: dict[str, str],
    column_mapping: dict[str, str | None],
    field: str,
) -> str | None:
    """Extract and clean a field from a CSV row.

    Args:
        row: CSV row as dictionary
        column_mapping: Mapping of field names to CSV columns
        field: Field name to extract

    Returns:
        Field value or None
    """
    col = column_mapping.get(field)
    if not col:
        return None
    return row.get(col, "").strip() or None


def _validate_csv_filename(filename: str | None) -> None:
    """Validate that an uploaded filename looks like a CSV file."""
    if not filename or not filename.lower().endswith(".csv"):
        raise ContactValidationError("File must be a CSV file")


async def _read_upload_file(file: UploadFile) -> bytes:
    """Read an uploaded file and map read failures to domain validation errors."""
    try:
        return await file.read()
    except Exception as exc:
        raise ContactValidationError(f"Failed to read file: {exc!s}") from exc


def _parse_explicit_mapping(column_mapping: str | None) -> dict[str, str] | None:
    """Parse optional JSON column mapping from upload form data."""
    if not column_mapping:
        return None
    try:
        parsed = json.loads(column_mapping)
    except json.JSONDecodeError as exc:
        raise ContactValidationError("Invalid column_mapping JSON") from exc
    if not isinstance(parsed, dict):
        raise ContactValidationError("Invalid column_mapping JSON")
    return {str(header): str(field) for header, field in parsed.items()}


def _validate_default_status(default_status: str) -> None:
    """Validate the default contact status used by CSV imports."""
    if default_status not in VALID_STATUSES:
        raise ContactValidationError(f"Invalid status. Must be: {', '.join(VALID_STATUSES)}")


def _read_csv_content(file_content: bytes) -> str:
    """Decode CSV file content, trying UTF-8 first then latin-1.

    Args:
        file_content: Raw file bytes

    Returns:
        Decoded string content
    """
    try:
        return file_content.decode("utf-8")
    except UnicodeDecodeError:
        return file_content.decode("latin-1")


def _process_csv_row(
    row: dict[str, str],
    row_num: int,
    column_mapping: dict[str, str | None],
    default_status: str,
    existing_phones: set[str],
    skip_duplicates: bool,
    errors: list[ImportErrorDetail],
) -> tuple[dict[str, Any] | None, bool]:
    """Process a single CSV row and return contact data or None if invalid.

    Args:
        row: CSV row as dictionary
        row_num: Row number (for error reporting)
        column_mapping: Mapping of field names to CSV columns
        default_status: Default status for contacts
        existing_phones: Set of existing phone numbers (normalized)
        skip_duplicates: Whether to skip duplicate phone numbers
        errors: List to append errors to

    Returns:
        Tuple of (contact_data or None, is_duplicate)
    """
    first_name = _get_csv_field(row, column_mapping, "first_name") or ""
    if not first_name:
        errors.append(
            ImportErrorDetail(row=row_num, field="first_name", error="First name is required")
        )
        return None, False

    phone_raw = _get_csv_field(row, column_mapping, "phone_number") or ""
    phone_number = clean_phone_number(phone_raw)
    if not phone_number:
        message = (
            "Phone number is required (used for voice/SMS follow-up)"
            if not phone_raw
            else f"Invalid phone number: {phone_raw}"
        )
        errors.append(ImportErrorDetail(row=row_num, field="phone_number", error=message))
        return None, False

    if skip_duplicates and phone_number in existing_phones:
        return None, True

    email = _get_csv_field(row, column_mapping, "email")
    if email and not validate_email(email):
        errors.append(
            ImportErrorDetail(row=row_num, field="email", error=f"Invalid email: {email}")
        )
        return None, False

    status_val = (_get_csv_field(row, column_mapping, "status") or "").lower()
    contact_status = default_status
    if status_val and status_val in VALID_STATUSES:
        contact_status = status_val
    elif status_val:
        errors.append(
            ImportErrorDetail(
                row=row_num, field="status", error=f"Invalid status '{status_val}', using default"
            )
        )

    tags_raw = _get_csv_field(row, column_mapping, "tags")
    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    return {
        "first_name": first_name,
        "last_name": _get_csv_field(row, column_mapping, "last_name"),
        "email": email,
        "phone_number": phone_number,
        "company_name": _get_csv_field(row, column_mapping, "company_name"),
        "status": contact_status,
        "tags": tags_list,
        "notes": _get_csv_field(row, column_mapping, "notes"),
        "address_line1": _get_csv_field(row, column_mapping, "address_line1"),
        "address_line2": _get_csv_field(row, column_mapping, "address_line2"),
        "address_city": _get_csv_field(row, column_mapping, "address_city"),
        "address_state": _get_csv_field(row, column_mapping, "address_state"),
        "address_zip": _get_csv_field(row, column_mapping, "address_zip"),
    }, False


class ContactImportService:
    """Service for importing contacts from CSV files."""

    def __init__(self, db: AsyncSession):
        """Initialize the import service.

        Args:
            db: Database session
        """
        self.db = db
        self.log = logger.bind(service="contact_import")

    async def preview_upload(self, file: UploadFile) -> dict[str, Any]:
        """Validate and preview an uploaded CSV file."""
        _validate_csv_filename(file.filename)
        content = await _read_upload_file(file)
        try:
            preview = self.preview_csv(content)
        except ValueError as exc:
            raise ContactValidationError(str(exc)) from exc

        return {
            "headers": preview["headers"],
            "sample_rows": preview["sample_rows"],
            "suggested_mapping": preview["suggested_mapping"],
            "contact_fields": CONTACT_FIELDS,
        }

    async def import_upload(
        self,
        *,
        workspace_id: uuid.UUID,
        file: UploadFile,
        skip_duplicates: bool = True,
        default_status: str = "new",
        source: str = "csv_import",
        column_mapping: str | None = None,
    ) -> ImportResult:
        """Validate upload form inputs and import contacts from an uploaded CSV file."""
        _validate_csv_filename(file.filename)
        _validate_default_status(default_status)
        content = await _read_upload_file(file)
        explicit_mapping = _parse_explicit_mapping(column_mapping)

        try:
            return await self.import_csv(
                workspace_id=workspace_id,
                file_content=content,
                skip_duplicates=skip_duplicates,
                default_status=default_status,
                source=source,
                explicit_mapping=explicit_mapping,
            )
        except ValueError as exc:
            raise ContactValidationError(str(exc)) from exc

    @staticmethod
    def preview_csv(file_content: bytes) -> dict[str, Any]:
        """Preview a CSV file: extract headers, sample rows, and suggest field mapping.

        Args:
            file_content: Raw CSV file content

        Returns:
            Dictionary with headers, sample_rows, and suggested_mapping
        """
        text_content = _read_csv_content(file_content)
        reader = csv.DictReader(io.StringIO(text_content))
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError("CSV file has no headers")

        sample_rows: list[dict[str, str]] = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            sample_rows.append(dict(row))

        # Build suggested mapping: csv_header -> field_name or None
        suggested_mapping: dict[str, str | None] = {}
        for header in headers:
            matched_field: str | None = None
            header_lower = header.lower().strip()
            for field_name, aliases in CSV_FIELD_MAPPING.items():
                if header_lower in [a.lower() for a in aliases]:
                    matched_field = field_name
                    break
            suggested_mapping[header] = matched_field

        return {
            "headers": headers,
            "sample_rows": sample_rows,
            "suggested_mapping": suggested_mapping,
        }

    async def import_csv(
        self,
        workspace_id: uuid.UUID,
        file_content: bytes,
        skip_duplicates: bool = True,
        default_status: str = "new",
        source: str = "csv_import",
        explicit_mapping: dict[str, str] | None = None,
    ) -> ImportResult:
        """Import contacts from CSV file.

        Args:
            workspace_id: The workspace UUID
            file_content: Raw CSV file content
            skip_duplicates: Whether to skip contacts with duplicate phone numbers
            default_status: Default status for new contacts
            source: Source identifier for imported contacts
            explicit_mapping: Optional mapping of csv_header -> field_name

        Returns:
            ImportResult with summary of import operation

        Raises:
            ValueError: If file format is invalid or required columns missing
        """
        _validate_default_status(default_status)
        self.log.info("import_started", workspace_id=str(workspace_id))

        # Parse CSV
        rows = await self._parse_csv(file_content)
        headers = list(rows[0].keys()) if rows else []

        # Build column mapping
        if explicit_mapping:
            # Invert: {csv_header: field_name} -> {field_name: csv_header}
            column_mapping: dict[str, str | None] = dict.fromkeys(CSV_FIELD_MAPPING, None)
            for csv_header, field_name in explicit_mapping.items():
                if field_name in column_mapping:
                    column_mapping[field_name] = csv_header
        else:
            column_mapping = {f: find_csv_column(headers, f) for f in CSV_FIELD_MAPPING}

        # Validate required fields
        if not column_mapping["first_name"]:
            raise ValueError("CSV must have a 'first_name' column")
        if not column_mapping["phone_number"]:
            raise ValueError(
                "A phone number column is required — every contact needs a phone number "
                "for voice/SMS follow-up. Map a phone column to continue."
            )

        # Get existing phone numbers
        existing_phones = (
            await self._get_existing_phones(workspace_id) if skip_duplicates else set()
        )

        # Process rows
        result = await self._process_rows(
            workspace_id=workspace_id,
            rows=rows,
            column_mapping=column_mapping,
            default_status=default_status,
            source=source,
            existing_phones=existing_phones,
            skip_duplicates=skip_duplicates,
        )

        self.log.info(
            "import_completed",
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped_duplicates,
        )

        return result

    async def _parse_csv(self, content: bytes) -> list[dict[str, str]]:
        """Parse CSV content into row dictionaries.

        Args:
            content: Raw CSV bytes

        Returns:
            List of row dictionaries

        Raises:
            ValueError: If CSV cannot be parsed
        """
        try:
            text_content = _read_csv_content(content)
        except Exception as e:
            raise ValueError(f"Failed to read file: {e!s}") from e

        try:
            reader = csv.DictReader(io.StringIO(text_content))
            headers = reader.fieldnames or []
        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e!s}") from e

        if not headers:
            raise ValueError("CSV file has no headers")

        return list(reader)

    async def _get_existing_phones(self, workspace_id: uuid.UUID) -> set[str]:
        """Get set of existing phone numbers in workspace.

        Args:
            workspace_id: The workspace UUID

        Returns:
            Set of normalized phone numbers
        """
        phone_result = await self.db.execute(
            select(Contact.phone_number).where(Contact.workspace_id == workspace_id)
        )
        existing_phones: set[str] = set()
        for db_row in phone_result:
            if db_row[0]:
                normalized = normalize_phone_safe(db_row[0])
                if normalized:
                    existing_phones.add(normalized)
        return existing_phones

    async def _process_rows(
        self,
        workspace_id: uuid.UUID,
        rows: list[dict[str, str]],
        column_mapping: dict[str, str | None],
        default_status: str,
        source: str,
        existing_phones: set[str],
        skip_duplicates: bool,
    ) -> ImportResult:
        """Process parsed rows and insert into database.

        Args:
            workspace_id: The workspace UUID
            rows: List of CSV row dictionaries
            column_mapping: Mapping of field names to CSV columns
            default_status: Default status for contacts
            source: Source identifier
            existing_phones: Set of existing phone numbers
            skip_duplicates: Whether to skip duplicates

        Returns:
            ImportResult with processing details
        """
        errors: list[ImportErrorDetail] = []
        created_contacts: list[Contact] = []
        skipped_duplicates_count = 0
        row_num = 1

        for row in rows:
            row_num += 1
            contact_data, is_dup = _process_csv_row(
                row,
                row_num,
                column_mapping,
                default_status,
                existing_phones,
                skip_duplicates,
                errors,
            )

            if is_dup:
                skipped_duplicates_count += 1
                continue

            if not contact_data:
                continue

            tag_names = contact_data.pop("tags", None)
            contact = Contact(
                workspace_id=workspace_id,
                source=source,
                **contact_data,
            )
            self.db.add(contact)
            await self.db.flush()
            await TagService(self.db).add_tags_to_contact(
                workspace_id=workspace_id,
                contact_id=contact.id,
                names=tag_names,
            )
            created_contacts.append(contact)
            existing_phones.add(contact_data["phone_number"])

        if created_contacts:
            await self.db.commit()

        return ImportResult(
            total_rows=row_num - 1,
            successful=len(created_contacts),
            failed=len([e for e in errors if "using default" not in e.error]),
            skipped_duplicates=skipped_duplicates_count,
            errors=errors[:100],  # Limit error list
            created_contacts=created_contacts[:100],  # Limit response size
        )

    @staticmethod
    def get_template_info() -> dict[str, Any]:
        """Get CSV import template information.

        Returns:
            Dictionary with template columns and example CSV
        """
        example_rows = [
            "first_name,last_name,phone_number,email,company_name,status,tags,notes,"
            "address_line1,address_city,address_state,address_zip",
            'John,Doe,+15551234567,john@example.com,Acme Inc,new,"vip,priority",,'
            "123 Main St,Austin,TX,78701",
            "Jane,Smith,5559876543,jane@example.com,Tech Corp,contacted,lead,,"
            "456 Oak Ave,Dallas,TX,75201",
        ]

        return {
            "columns": [
                {"name": "first_name", "required": True, "description": "First name"},
                {"name": "last_name", "required": False, "description": "Last name"},
                {"name": "email", "required": False, "description": "Email address"},
                {"name": "phone_number", "required": True, "description": "Phone"},
                {"name": "company_name", "required": False, "description": "Company"},
                {"name": "status", "required": False, "description": "Lead status"},
                {"name": "tags", "required": False, "description": "Comma-separated"},
                {"name": "notes", "required": False, "description": "Notes"},
                {"name": "address_line1", "required": False, "description": "Street address"},
                {"name": "address_line2", "required": False, "description": "Unit/suite"},
                {"name": "address_city", "required": False, "description": "City"},
                {"name": "address_state", "required": False, "description": "State/province"},
                {"name": "address_zip", "required": False, "description": "Zip/postal code"},
            ],
            "example_csv": "\n".join(example_rows),
            "supported_aliases": CSV_FIELD_MAPPING,
            # Named exporter presets the import preview auto-detects. Keyed by
            # source slug → {source_csv_header: contact_field}. The frontend can
            # surface "Importing from Jobber?" and apply this mapping directly.
            "presets": {"jobber": JOBBER_CSV_PRESET},
        }
