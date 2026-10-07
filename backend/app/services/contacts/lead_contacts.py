"""Resolve a CRM contact from a public lead-capture submission.

Public capture surfaces (offer opt-ins) collect whatever the operator asked for
— often only an email. This module turns that submission into exactly one
workspace-scoped :class:`~app.models.contact.Contact`:

* identifiers are normalized (email trimmed, phone parsed to E.164) and
  rejected when malformed instead of being silently dropped;
* deduplication goes through the deterministic ``email_hash``/``phone_hash``
  lookup columns (the plaintext columns are Fernet-encrypted, so comparing
  them directly never matches);
* an existing contact is only *filled in* — values the operator already has
  are never overwritten;
* no phone number or messaging consent is ever invented.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.encryption import hash_phone, hash_value
from app.models.contact import Contact
from app.services.contacts.contact_import import clean_phone_number, validate_email

# Placeholder historically written when a lead gave no name; treated as "no name"
# so a later submission can fill it in.
UNKNOWN_FIRST_NAME = "Unknown"
_FIRST_NAME_MAX = 100
_LAST_NAME_MAX = 100


class LeadIdentityError(ValueError):
    """Raised when submitted lead fields are malformed or insufficient."""


@dataclass(frozen=True)
class LeadIdentity:
    """Normalized identifying fields from one lead-capture submission."""

    email: str | None
    phone_number: str | None
    name: str | None


@dataclass(frozen=True)
class LeadContactResult:
    """Outcome of resolving a submission to a contact."""

    contact: Contact
    created: bool


def normalize_lead_identity(
    *,
    email: str | None,
    phone_number: str | None,
    name: str | None,
) -> LeadIdentity:
    """Normalize submitted fields, raising :class:`LeadIdentityError` if invalid.

    Blank strings count as "not provided". A provided-but-malformed email or
    phone is an error rather than being dropped, so the caller never reports
    success for data it could not store.
    """
    clean_email = (email or "").strip() or None
    if clean_email is not None and not validate_email(clean_email):
        raise LeadIdentityError("Please enter a valid email address")

    raw_phone = (phone_number or "").strip() or None
    clean_phone: str | None = None
    if raw_phone is not None:
        clean_phone = clean_phone_number(raw_phone)
        if clean_phone is None:
            raise LeadIdentityError("Please enter a valid phone number")

    clean_name = " ".join((name or "").split()) or None
    return LeadIdentity(email=clean_email, phone_number=clean_phone, name=clean_name)


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    first, _, last = name.partition(" ")
    return first[:_FIRST_NAME_MAX], (last[:_LAST_NAME_MAX] or None)


async def _find_by_hash(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    column: InstrumentedAttribute[str | None],
    value: str,
) -> Contact | None:
    # Oldest match wins so repeat submissions keep attaching to the same row
    # even if historical duplicates exist (no unique constraint on the hashes).
    result = await db.execute(
        select(Contact)
        .where(Contact.workspace_id == workspace_id, column == value)
        .order_by(Contact.id)
        .limit(1)
    )
    return result.scalars().first()


async def find_or_create_lead_contact(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    identity: LeadIdentity,
    source: str,
    note: str | None = None,
) -> LeadContactResult:
    """Find the workspace contact matching ``identity`` or create one.

    Lookup order is email, then phone (matching the historical offer opt-in
    precedence). Existing contacts only gain fields they are missing. The
    session is flushed, not committed — the caller owns the transaction.
    """
    if identity.email is None and identity.phone_number is None:
        raise LeadIdentityError("Email or phone number is required")

    contact: Contact | None = None
    if identity.email is not None:
        contact = await _find_by_hash(
            db, workspace_id, Contact.email_hash, hash_value(identity.email)
        )
    if contact is None and identity.phone_number is not None:
        contact = await _find_by_hash(
            db, workspace_id, Contact.phone_hash, hash_phone(identity.phone_number)
        )

    first_name, last_name = _split_name(identity.name)

    if contact is None:
        contact = Contact(
            workspace_id=workspace_id,
            first_name=first_name or UNKNOWN_FIRST_NAME,
            last_name=last_name,
            email=identity.email,
            email_hash=hash_value(identity.email) if identity.email else None,
            phone_number=identity.phone_number,
            phone_hash=hash_phone(identity.phone_number) if identity.phone_number else None,
            status="new",
            source=source,
            notes=note,
        )
        db.add(contact)
        await db.flush()
        return LeadContactResult(contact=contact, created=True)

    # Fill gaps only; never overwrite what the operator already has.
    if identity.email and not contact.email:
        contact.email = identity.email
        contact.email_hash = hash_value(identity.email)
    if identity.phone_number and not contact.phone_number:
        contact.phone_number = identity.phone_number
        contact.phone_hash = hash_phone(identity.phone_number)
    if first_name and contact.first_name in ("", UNKNOWN_FIRST_NAME):
        contact.first_name = first_name
        if last_name and not contact.last_name:
            contact.last_name = last_name
    if note and note not in (contact.notes or ""):
        contact.notes = f"{contact.notes}\n{note}" if contact.notes else note
    await db.flush()
    return LeadContactResult(contact=contact, created=False)
