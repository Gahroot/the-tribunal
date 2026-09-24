"""Evidence-gated sales proof from dated, comparable campaign funnel exports.

Never publish a case study or benchmark comparison without source records and
permission. The user-provided $224/$487 figures are context, not measured here.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class FunnelPeriod:
    label: str
    source: str
    starts_at: str
    ends_at: str
    attempts: int
    connected: int
    qualified: int
    booked: int
    qualified_meetings: int
    shown: int
    total_cost_usd: Decimal

    def __post_init__(self) -> None:
        if not all((self.label, self.source, self.starts_at, self.ends_at)):
            raise ValueError("Label, evidence source, and period dates are required")
        try:
            start = date.fromisoformat(self.starts_at)
            end = date.fromisoformat(self.ends_at)
        except ValueError as exc:
            raise ValueError("Period dates must be ISO calendar dates") from exc
        if start >= end:
            raise ValueError("Period must end after it starts")
        counts = (
            self.attempts,
            self.connected,
            self.qualified,
            self.booked,
            self.qualified_meetings,
            self.shown,
        )
        if any(n < 0 for n in counts):
            raise ValueError("Counts cannot be negative")
        if (
            self.connected > self.attempts
            or self.qualified > self.attempts
            or self.booked > self.attempts
            or self.shown > self.booked
            or self.qualified_meetings > min(self.qualified, self.booked)
        ):
            raise ValueError("Funnel counts are inconsistent")
        if not self.total_cost_usd.is_finite() or self.total_cost_usd < 0:
            raise ValueError("Cost must be finite and nonnegative")


def benchmark_context() -> dict:
    """Arithmetic on brief-supplied figures, NOT an observed or sourced result.

    Do not use as customer proof without independently validating denominators,
    cost inclusion, dates and the human-only benchmark source.
    """
    hybrid = Decimal("224")
    human_only = Decimal("487")
    return {
        "hybrid_usd": hybrid,
        "human_only_usd": human_only,
        "difference_usd": human_only - hybrid,
        "lower_fraction": (human_only - hybrid) / human_only,
        "source": "user brief; independently unverified",
        "publishable": False,
    }


def _rate(numerator: int, denominator: int) -> Decimal | None:
    return Decimal(numerator) / Decimal(denominator) if denominator else None


def _delta(before: Decimal | None, after: Decimal | None) -> Decimal | None:
    """Percentage-point change for rates, not relative percent growth."""
    return (after - before) * 100 if before is not None and after is not None else None


def build_proof_pack(before: FunnelPeriod, after: FunnelPeriod) -> dict:
    """Compute comparable funnel rates and lift; leave unknowns explicitly null.

    Both windows need independent source references; operator must verify cohort,
    attribution, costs and permission before publishing any result.
    """
    if before.source == after.source:
        raise ValueError("Each period needs its own evidence source")
    if before.ends_at > after.starts_at:
        raise ValueError("Comparison windows must not overlap")

    def metrics(period: FunnelPeriod) -> dict:
        return {
            "attempts": period.attempts,
            "connected": period.connected,
            "qualified": period.qualified,
            "booked": period.booked,
            "qualified_meetings": period.qualified_meetings,
            "shown": period.shown,
            "connect_rate": _rate(period.connected, period.attempts),
            "qualification_rate": _rate(period.qualified, period.attempts),
            "booking_rate": _rate(period.booked, period.attempts),
            "show_rate": _rate(period.shown, period.booked),
            "cost_per_qualified_meeting_usd": (
                period.total_cost_usd / period.qualified_meetings
                if period.qualified_meetings
                else None
            ),
        }

    old, new = metrics(before), metrics(after)
    return {
        "before": old,
        "after": new,
        "lift_percentage_points": {
            key: _delta(old[key], new[key])
            for key in ("connect_rate", "qualification_rate", "booking_rate", "show_rate")
        },
        "sources": (before.source, after.source),
        "periods": ((before.starts_at, before.ends_at), (after.starts_at, after.ends_at)),
        "publishable": False,  # Human review of evidence, consent and benchmark basis is required.
    }
