"""Hiring-signal provider (config-gated stub).

A company actively hiring — especially for roles tied to your offer (e.g.
"Head of Growth", "Paid Media Manager") — is a strong buying signal. Real
coverage needs a licensed jobs data source; until ``hiring_signal_api_key`` is
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


class HiringSignalProvider(BaseSignalProvider):
    """Emit a ``hiring`` signal once a jobs data source is configured."""

    signal_source: ClassVar[str] = "hiring"

    def is_enabled(self) -> bool:
        return bool((settings.hiring_signal_api_key or "").strip())

    async def collect(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        # No configured data source -> no signal. A licensed adapter lands here.
        return []
