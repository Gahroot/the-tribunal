"""Unit tests for the stage-type -> opportunity-status contract."""

import pytest

from app.services.exceptions import ValidationError
from app.services.opportunities.opportunity_service import resolve_stage_move_status


@pytest.mark.parametrize(
    ("stage_type", "current", "requested", "expected"),
    [
        ("won", "open", None, "won"),
        ("lost", "open", None, "lost"),
        ("won", "lost", None, "won"),
        ("won", "open", "won", "won"),
        ("lost", "abandoned", None, "lost"),
        # Moving back to an active stage reopens an outcome-closed deal.
        ("active", "won", None, "open"),
        ("active", "lost", None, "open"),
        # Active-to-active moves keep the current open/abandoned status.
        ("active", "open", None, "open"),
        ("active", "abandoned", None, "abandoned"),
        # Explicit non-outcome status alongside an active stage is honoured.
        ("active", "won", "abandoned", "abandoned"),
        ("active", "abandoned", "open", "open"),
    ],
)
def test_resolve_stage_move_status(
    stage_type: str, current: str, requested: str | None, expected: str
) -> None:
    assert resolve_stage_move_status(stage_type, current, requested) == expected


@pytest.mark.parametrize(
    ("stage_type", "requested"),
    [("won", "lost"), ("won", "open"), ("lost", "won"), ("active", "won"), ("active", "lost")],
)
def test_conflicting_status_is_rejected(stage_type: str, requested: str) -> None:
    with pytest.raises(ValidationError):
        resolve_stage_move_status(stage_type, "open", requested)
