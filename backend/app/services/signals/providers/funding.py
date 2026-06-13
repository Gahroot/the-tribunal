"""Funding-signal provider (config-gated stub).

A recent raise means budget + urgency — a strong buying signal. Real coverage
needs a licensed funding data source; until ``funding_signal_api_key`` is
configured this provider stays disabled and emits **no fabricated data**.

The clean seam (``is_enabled`` + ``collect``) lets a real adapter drop in
without touching the aggregator.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lead_prospect import LeadProspect
from app.services.signals.protocol import BaseSignalProvider
from app.services.signals.types import CollectedSignal


class FundingSignalProvider(BaseSignalProvider):
    """Emit a ``funding`` signal once a funding data source is configured."""

    signal_source: ClassVar[str] = "funding"

    def is_enabled(self) -> bool:
        return bool((settings.funding_signal_api_key or "").strip())

    async def collect(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        # No configured data source -> no signal. A licensed adapter lands here.
        return []
