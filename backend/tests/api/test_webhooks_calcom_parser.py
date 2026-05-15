"""Tests for ``app.api.webhooks.calcom_parser``.

The parser module is two functions:

- :func:`apply_contact_tag` — pure mutation helper that adds a tag to a
  contact only when not already present.
- :func:`find_contact_by_attendee` — SQLAlchemy lookup that prefers an
  exact-email match, falls back to a phone-suffix LIKE query.

Both are exercised here with mocked async sessions and ORM stand-ins,
plus real-shape Cal.com attendee payloads loaded from
``tests/fixtures/webhooks/calcom/``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.webhooks.calcom_parser import (
    apply_contact_tag,
    find_contact_by_attendee,
)
from tests.fixtures.webhooks import load_fixture

# --------------------------------------------------------------------------- #
# apply_contact_tag — pure helper, no I/O
# --------------------------------------------------------------------------- #


def test_apply_contact_tag_adds_to_empty_list() -> None:
    contact = MagicMock()
    contact.tags = []

    apply_contact_tag(contact, "appointment-scheduled")

    assert contact.tags == ["appointment-scheduled"]


def test_apply_contact_tag_appends_when_missing() -> None:
    contact = MagicMock()
    contact.tags = ["lead", "warm"]

    apply_contact_tag(contact, "appointment-scheduled")

    assert contact.tags == ["lead", "warm", "appointment-scheduled"]


def test_apply_contact_tag_is_idempotent() -> None:
    """Re-applying an existing tag must not duplicate or mutate ordering."""
    contact = MagicMock()
    contact.tags = ["lead", "appointment-scheduled"]
    original = list(contact.tags)

    apply_contact_tag(contact, "appointment-scheduled")

    assert contact.tags == original


def test_apply_contact_tag_treats_none_tags_as_empty() -> None:
    """Contacts whose ``tags`` column is NULL must still accept new tags."""
    contact = MagicMock()
    contact.tags = None

    apply_contact_tag(contact, "no-show")

    assert contact.tags == ["no-show"]


def test_apply_contact_tag_does_not_mutate_input_list_in_place() -> None:
    """Implementation must return a *new* list to keep SQLAlchemy change-detection happy.

    SQLAlchemy ORM only marks ``tags`` dirty when the attribute is
    reassigned (not when an existing list is mutated in place). This
    guards against a regression where ``apply_contact_tag`` would call
    ``contact.tags.append(...)`` and silently fail to persist.
    """
    contact = MagicMock()
    original_list: list[str] = ["lead"]
    contact.tags = original_list

    apply_contact_tag(contact, "appointment-scheduled")

    assert original_list == ["lead"]  # untouched
    assert contact.tags == ["lead", "appointment-scheduled"]
    assert contact.tags is not original_list


# --------------------------------------------------------------------------- #
# find_contact_by_attendee — DB lookups
# --------------------------------------------------------------------------- #


def _result_with(value: Any) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


async def test_find_contact_matches_on_email_first() -> None:
    """Email is the primary identifier; phone is not consulted on hit."""
    contact = MagicMock()
    contact.id = 7

    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(contact))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email="client@example.com",
        phone="+14155552671",
        db=db,
        log=log,
    )

    assert found is contact
    # Email-only path → exactly one SELECT.
    assert db.execute.await_count == 1
    log.warning.assert_not_called()


async def test_find_contact_falls_back_to_phone_when_email_misses() -> None:
    """No email hit → match by last-10-digits suffix."""
    contact = MagicMock()
    contact.id = 11

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[_result_with(None), _result_with(contact)]
    )
    log = MagicMock()

    found = await find_contact_by_attendee(
        email="unknown@example.com",
        phone="+1 (555) 123-4567",  # mixed format
        db=db,
        log=log,
    )

    assert found is contact
    assert db.execute.await_count == 2
    log.info.assert_any_call("contact_matched_by_phone_fallback", contact_id=11)


async def test_find_contact_phone_only_when_email_missing() -> None:
    """Phone-only attendees (no email) still resolve via phone suffix."""
    contact = MagicMock()
    contact.id = 12

    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(contact))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email=None,
        phone="+14155552671",
        db=db,
        log=log,
    )

    assert found is contact
    # No email → only the phone-fallback SELECT fires.
    assert db.execute.await_count == 1


async def test_find_contact_short_phone_is_skipped() -> None:
    """Phones with fewer than 10 digits cannot identify a contact."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(None))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email=None,
        phone="12345",  # only 5 digits → unusable
        db=db,
        log=log,
    )

    assert found is None
    # No queries issued for the short phone.
    db.execute.assert_not_called()
    log.warning.assert_called_once()


async def test_find_contact_logs_warning_when_nothing_matches() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(None))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email="nobody@example.com",
        phone="+14155552673",
        db=db,
        log=log,
    )

    assert found is None
    log.warning.assert_called_once()
    args, kwargs = log.warning.call_args
    assert args[0] == "contact_not_found"
    assert kwargs == {"email": "nobody@example.com", "phone": "+14155552673"}


async def test_find_contact_handles_none_email_and_phone() -> None:
    """Both identifiers missing → no DB calls, warning logged, None returned."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(None))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email=None,
        phone=None,
        db=db,
        log=log,
    )

    assert found is None
    db.execute.assert_not_called()
    log.warning.assert_called_once()


# --------------------------------------------------------------------------- #
# Real-payload smoke test
# --------------------------------------------------------------------------- #


@pytest.fixture
def booking_created_payload() -> dict[str, Any]:
    return load_fixture("calcom", "booking_created.json")


async def test_find_contact_with_real_calcom_attendee_payload(
    booking_created_payload: dict[str, Any],
) -> None:
    """End-to-end shape: extract attendee from real Cal.com payload."""
    attendee = booking_created_payload["data"]["attendees"][0]
    email = attendee.get("email")
    phone = attendee.get("phoneNumber") or attendee.get("phone")

    contact = MagicMock()
    contact.id = 42

    db = MagicMock()
    db.execute = AsyncMock(return_value=_result_with(contact))
    log = MagicMock()

    found = await find_contact_by_attendee(
        email=email, phone=phone, db=db, log=log,
    )

    assert found is contact
    # Attendee carries an email — phone-fallback SELECT must NOT fire.
    assert db.execute.await_count == 1
