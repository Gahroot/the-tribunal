"""Running-ads signal from the ad-intelligence layer.

If an :class:`~app.models.ad_advertiser.AdAdvertiser` is already linked to the
prospect (``AdAdvertiser.prospect_id``), this provider maps its computed
opportunity signal into a normalized ``running_ads`` :class:`CollectedSignal`.
It does **not** call any ad-library API — it reuses what the ad-library
discovery / monitor workers already persisted.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ad_advertiser import AdAdvertiser
from app.models.lead_prospect import LeadProspect
from app.models.prospect_signal import ProspectSignalType
from app.services.signals.protocol import BaseSignalProvider
from app.services.signals.types import CollectedSignal


class AdsSignalProvider(BaseSignalProvider):
    """Emit a ``running_ads`` signal from a linked advertiser's ad data."""

    signal_source: ClassVar[str] = "ad_library"

    async def collect(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        rows = await db.execute(
            select(AdAdvertiser)
            .where(AdAdvertiser.prospect_id == prospect.id)
            .order_by(AdAdvertiser.opportunity_score.desc())
        )
        advertiser = rows.scalars().first()
        if advertiser is None:
            return []

        running_days = advertiser.longest_running_active_days or 0
        # Only emit when the advertiser is actually running ads now.
        if not advertiser.is_active and running_days <= 0:
            return []

        strength = int(advertiser.opportunity_score or 0)
        summary = self._summary(advertiser, running_days)
        payload = {
            "platform": advertiser.platform.value,
            "opportunity_score": advertiser.opportunity_score,
            "longest_running_active_days": running_days,
            "active_ad_count": advertiser.active_ad_count,
            "distinct_creative_count": advertiser.distinct_creative_count,
            "creative_refresh_rate": advertiser.creative_refresh_rate,
            "continuity_score": advertiser.continuity_score,
            "example_creative": advertiser.example_creative,
            "page_url": advertiser.page_url,
            "advertiser_name": advertiser.advertiser_name,
        }
        return [
            CollectedSignal(
                signal_type=ProspectSignalType.RUNNING_ADS.value,
                strength=strength,
                source=self.signal_source,
                summary=summary,
                payload=payload,
            )
        ]

    @staticmethod
    def _summary(advertiser: AdAdvertiser, running_days: int) -> str:
        platform = advertiser.platform.value.capitalize()
        if running_days > 0:
            return f"Running {platform} ads — longest active creative up for {running_days} days."
        return f"Currently running {platform} ads ({advertiser.active_ad_count} active)."
