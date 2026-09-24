from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai.ivr.booking_menu import BookingMenuNavigator
from app.services.ai.tool_executor import VoiceToolExecutor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("menu", "goal", "digit"),
    [
        ("Press 1 to book. Press 2 for billing.", "book", "1"),
        ("For appointments press 3. For billing press 2.", "book", "3"),
        ("Press 0 for an operator. Press 1 to book.", "human", "0"),
        ("Press star to repeat. Press pound to go back.", "repeat", "*"),
        ("Press star to repeat. Press pound to go back.", "back", "#"),
    ],
)
async def test_announced_option_sends_exact_tone(menu, goal, digit):
    ex = VoiceToolExecutor(agent=SimpleNamespace())
    ex._execute_send_dtmf = AsyncMock(return_value={"success": True})
    result = await ex.execute("navigate_booking_menu", {"transcript": menu, "goal": goal})
    assert result["success"]
    assert result["navigation_only"]
    ex._execute_send_dtmf.assert_awaited_once_with(digit)
    assert ex.booking_flow.state == "idle"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "menu",
    [
        "Please hold.",
        "Press 1 for billing.",
        "Press 1 to book. Press 2 for appointments.",
        "Press 123 to book.",
        "Press 1 to cancel an appointment.",
        "Press 2 to reschedule an appointment.",
        "Press 1 if you do not want to book.",
    ],
)
async def test_no_guessed_or_ambiguous_digits(menu):
    send = AsyncMock()
    assert not (await BookingMenuNavigator().navigate(menu, "book", send))["success"]
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_menu_steps_and_loop_limit():
    navigator = BookingMenuNavigator()
    send = AsyncMock(return_value={"success": True})
    assert (await navigator.navigate("Press 1 to book.", "book", send))["success"]
    # The same digit is allowed at a genuinely different menu level.
    assert (await navigator.navigate("Press 1 for appointments with Alice.", "book", send))[
        "success"
    ]
    assert not (await navigator.navigate("PRESS 1 TO BOOK.", "book", send))["success"]
    for i in range(6):
        assert (await navigator.navigate(f"Press 2 to book calendar {i}.", "book", send))["success"]
    assert not (await navigator.navigate("Press 3 to book another.", "book", send))["success"]
    assert send.await_count == 8


@pytest.mark.asyncio
async def test_failed_tone_is_not_repeated():
    send = AsyncMock(return_value={"success": False})
    navigator = BookingMenuNavigator()
    await navigator.navigate("Press 1 to book.", "book", send)
    await navigator.navigate("Press 1 to book.", "book", send)
    send.assert_awaited_once()
