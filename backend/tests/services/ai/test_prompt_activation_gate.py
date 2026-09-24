"""Automatic promotion requires both independent outcome and rubric evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.workers.prompt_improvement_worker import PromptImprovementWorker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "bookings", "shown", "review", "expected"),
    [
        (0.9, 0, 0, False, False),  # Transcript-only success is not a booking.
        (0.5, 3, 0, False, False),  # Booking alone is not sufficient quality.
        (0.9, 3, 0, True, False),  # Review-needed evidence cannot auto-promote.
        (0.9, 3, 0, False, True),
        (0.9, 0, 2, False, True),  # Attended appointments are real outcomes too.
    ],
)
async def test_promotion_gate(score, bookings, shown, review, expected):
    rows = [
        (
            {"judge": {"score": score, "human_review": review}},
            "success" if i < bookings else None,
            i < shown,
        )
        for i in range(10)
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    worker = PromptImprovementWorker()
    version = SimpleNamespace(id="test-version")
    assert await worker._can_auto_activate(db, version) is expected
