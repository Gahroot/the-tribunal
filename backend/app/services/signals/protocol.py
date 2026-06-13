"""Protocol + base class for buying-signal providers.

A provider inspects a :class:`~app.models.lead_prospect.LeadProspect` (and may
reach out to already-stored data or the web) and returns the typed signals it
found. Providers must be cheap and side-effect free: persistence + score
folding is the aggregator's job, not the provider's.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_prospect import LeadProspect
from app.services.signals.types import CollectedSignal


@runtime_checkable
class SignalProvider(Protocol):
    """Structural interface every signal provider must satisfy."""

    signal_source: ClassVar[str]
    """Stable provider key stamped onto emitted signals (``"ad_library"``)."""

    def is_enabled(self) -> bool:
        """Whether this provider is configured to run.

        Config-gated providers (hiring, funding) return ``False`` until their
        API keys are set, so the aggregator skips them with no fabricated data.
        """
        ...

    async def collect(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        """Return the signals observed for ``prospect`` (no persistence)."""
        ...


class BaseSignalProvider:
    """Convenience base: enabled-by-default, no-op collect."""

    signal_source: ClassVar[str]

    def is_enabled(self) -> bool:
        return True

    async def collect(
        self, db: AsyncSession, prospect: LeadProspect
    ) -> list[CollectedSignal]:  # pragma: no cover - abstract
        raise NotImplementedError
