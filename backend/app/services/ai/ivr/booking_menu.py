"""Bounded, explicit-option navigation for external appointment phone menus."""

import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.ai.ivr.navigator import ScriptedNavigator


class BookingMenuNavigator:
    """No speculative digits, no automatic pound suffix, no repeated-menu loops."""

    _WORDS = {
        "book": {"appointment", "appointments", "book", "booking", "schedule", "scheduling"},
        "human": {"operator", "representative", "receptionist", "person", "agent"},
        "repeat": {"repeat", "again"},
        "back": {"back", "previous", "main"},
    }

    _NOT_NEW_BOOKING = {
        "cancel",
        "cancellation",
        "canceling",
        "cancelling",
        "reschedule",
        "rescheduling",
        "existing",
        "not",
        "don't",
    }

    def _matches(self, description: str, goal: str) -> bool:
        words = set(re.findall(r"[\w']+", description))
        if goal == "book" and words & self._NOT_NEW_BOOKING:
            return False
        return bool(words & self._WORDS.get(goal, set()))

    def __init__(self) -> None:
        self._attempted: set[tuple[str, str]] = set()
        self._parser = ScriptedNavigator()

    async def navigate(
        self,
        transcript: str,
        goal: str,
        send: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        options = self._parser.extract_menu_options(transcript)
        matches = [o for o in options if len(o.digit) == 1 and self._matches(o.description, goal)]
        if len(matches) != 1:
            return {
                "success": False,
                "message": "No unambiguous announced option. Listen or ask for help.",
            }
        digit = matches[0].digit
        # Ignore capitalization, whitespace and ordering when identifying repeated menus.
        menu = "|".join(
            sorted(f"{o.digit}:{' '.join(re.findall(r'\w+', o.description))}" for o in options)
        )
        key = (menu, digit)
        if key in self._attempted or len(self._attempted) >= 8:
            return {
                "success": False,
                "message": "Menu repeated or navigation limit reached. Ask for help.",
            }
        # Record BEFORE awaiting: a cancellation or ambiguous send must not duplicate tones.
        self._attempted.add(key)
        result = await send(digit)
        return {**result, "digit": digit, "navigation_only": True}
