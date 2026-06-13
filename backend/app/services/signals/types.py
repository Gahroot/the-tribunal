"""Value types for the buying-signal layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class CollectedSignal:
    """One typed buying signal a provider observed for a prospect.

    The aggregator upserts this into a
    :class:`~app.models.prospect_signal.ProspectSignal` row (queryable) and
    appends ``evidence`` to the prospect's outreach evidence blob.

    Attributes:
        signal_type: Canonical type (matches ``ProspectSignalType`` values;
            stored as plain string so new providers need no enum migration).
        strength: Normalized 0..100 confidence/intensity used for ranking.
        source: Provider key the signal came from (e.g. ``"ad_library"``).
        summary: One-line, human-readable description for the UI + outreach.
        payload: Structured facts backing the strength score.
        evidence: Outreach-ready blob appended to ``LeadProspect.evidence``;
            defaults to a compact projection of ``payload`` when omitted.
        observed_at: When the signal was observed.
    """

    signal_type: str
    strength: int
    source: str
    summary: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] | None = None
    observed_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        # Clamp strength into 0..100 without mutating frozen attrs elsewhere.
        clamped = max(0, min(100, int(self.strength)))
        if clamped != self.strength:
            object.__setattr__(self, "strength", clamped)

    def evidence_blob(self) -> dict[str, Any]:
        """Return the outreach-ready evidence dict for this signal."""
        if self.evidence is not None:
            return self.evidence
        blob: dict[str, Any] = {
            "type": "signal",
            "signal_type": self.signal_type,
            "source": self.source,
            "strength": self.strength,
        }
        if self.summary:
            blob["summary"] = self.summary
        if self.payload:
            blob["payload"] = self.payload
        return blob
