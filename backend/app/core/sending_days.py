"""Campaign ``sending_days`` encoding — the single, documented day contract.

Every SMS/voice campaign (and message test that converts into one) stores
``sending_days`` as Python ``date.weekday()`` integers, evaluated on the
campaign's *local* calendar date (``campaign.timezone``):

    Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6

So Monday–Friday is ``[0, 1, 2, 3, 4]``. This is NOT JavaScript's
``Date.getDay()`` (Sunday=0); the dashboard's day picker
(``frontend/src/lib/constants.ts``) uses this same Monday=0 encoding.

``None`` (or a legacy empty list) means "every day". New API input must not
send an empty list: an operator who deselects every day would otherwise get
the opposite of what they chose.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, Field

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)
WEEKDAYS: tuple[int, ...] = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY)
DAY_NAMES: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

SENDING_DAYS_DESCRIPTION = (
    "Days of the week sending is allowed, evaluated in the campaign timezone. "
    "Python weekday encoding: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, "
    "Friday=4, Saturday=5, Sunday=6 (Mon-Fri = [0,1,2,3,4]); NOT JavaScript "
    "getDay(). null means every day."
)


def normalize_sending_days(value: list[int] | None) -> list[int] | None:
    """Validate API input against the contract; return sorted unique days."""
    if value is None:
        return None
    if not value:
        raise ValueError(
            "sending_days must include at least one day (Monday=0 … Sunday=6); "
            "send null to allow every day"
        )
    invalid = sorted({day for day in value if not MONDAY <= day <= SUNDAY})
    if invalid:
        raise ValueError(f"sending_days values must be 0-6 (Monday=0 … Sunday=6); got {invalid}")
    return sorted(set(value))


def is_sending_day(sending_days: Sequence[int] | None, local_day: date) -> bool:
    """Whether ``local_day`` (already in the campaign timezone) may send.

    ``None``/empty keeps the legacy "every day" behaviour.
    """
    return not sending_days or local_day.weekday() in sending_days


SendingDaysInput = Annotated[
    list[int] | None,
    AfterValidator(normalize_sending_days),
    Field(description=SENDING_DAYS_DESCRIPTION),
]
"""Request field type: validates and normalises against the contract."""

SendingDaysOutput = Annotated[list[int] | None, Field(description=SENDING_DAYS_DESCRIPTION)]
"""Response field type: documents the contract without rejecting legacy rows."""
