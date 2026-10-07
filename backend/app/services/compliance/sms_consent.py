"""Record operator-attested SMS consent for contacts.

Consent is never inferred (e.g. from an import). An operator must name where
consent came from and attest to it; the record is stored on the contact with
who recorded it and when. Workspace opt-outs always win: numbers on the
workspace opt-out list are skipped, never re-enabled.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, get_args

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.compliance.outbound_compliance import OutboundComplianceService
from app.services.rate_limiting.opt_out_manager import OptOutManager

logger = structlog.get_logger()

SmsConsentSource = Literal[
    "web_form",
    "paper_form",
    "text_keyword",
    "verbal_recorded",
    "other_documented",
]
SMS_CONSENT_SOURCES: tuple[str, ...] = get_args(SmsConsentSource)
MAX_CONSENT_BATCH = 10_000


class SmsConsentValidationError(ValueError):
    """Raised when a consent record request is invalid."""


@dataclass(slots=True)
class SmsConsentRecordResult:
    updated: int = 0
    already_opted_in: int = 0
    skipped_opted_out: list[int] = field(default_factory=list)
    not_found: list[int] = field(default_factory=list)


async def record_sms_consent(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    contact_ids: list[int],
    source: str,
    collected_at: datetime | None,
    notes: str | None,
    recorded_by_user_id: int,
    opt_out_manager: OptOutManager | None = None,
) -> SmsConsentRecordResult:
    """Mark workspace contacts as SMS opted-in from an attested consent record."""
    if not contact_ids:
        raise SmsConsentValidationError("No contact IDs provided")
    if source not in SMS_CONSENT_SOURCES:
        raise SmsConsentValidationError("Unknown consent source")
    now = datetime.now(UTC)
    if collected_at is not None and collected_at > now:
        raise SmsConsentValidationError("Consent collection date cannot be in the future")

    unique_ids = list(dict.fromkeys(contact_ids))
    result = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.id.in_(unique_ids))
    )
    contacts = {contact.id: contact for contact in result.scalars().all()}
    manager = opt_out_manager or OptOutManager()
    opted_out = await manager.opted_out_numbers(
        workspace_id, (contact.phone_number for contact in contacts.values()), db
    )

    outcome = SmsConsentRecordResult()
    note = f"Recorded by user {recorded_by_user_id} on {now.date().isoformat()}"
    if notes:
        note = f"{note}: {notes.strip()}"
    for contact_id in unique_ids:
        contact = contacts.get(contact_id)
        if contact is None:
            outcome.not_found.append(contact_id)
            continue
        if contact.phone_number in opted_out:
            outcome.skipped_opted_out.append(contact_id)
            continue
        if contact.sms_consent_status == OutboundComplianceService.OPTED_IN:
            outcome.already_opted_in += 1
            continue
        contact.sms_consent_status = OutboundComplianceService.OPTED_IN
        contact.sms_consent_source = source
        contact.sms_consent_collected_at = collected_at or now
        contact.sms_consent_notes = note
        outcome.updated += 1

    logger.info(
        "sms_consent_recorded",
        workspace_id=str(workspace_id),
        recorded_by_user_id=recorded_by_user_id,
        source=source,
        updated=outcome.updated,
        skipped_opted_out=len(outcome.skipped_opted_out),
        not_found=len(outcome.not_found),
    )
    return outcome
