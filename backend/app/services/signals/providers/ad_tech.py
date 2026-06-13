"""Ad/analytics-tech signal from installed website pixels.

Reuses :meth:`WebsiteScraperService._detect_ad_pixels` to detect whether the
prospect's site has Meta/Google/etc. ad + analytics pixels installed. A site
wired with a Meta Pixel + Google Ads conversion tag is actively advertising even
when it isn't in a public ad library — a strong buying signal.

Pixel detection is pure (:func:`signal_from_pixels`); the provider only adds the
website fetch. A pre-scraped ``pixels`` dict or a shared scraper can be injected
to avoid re-fetching a page the enrichment worker already pulled.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_prospect import LeadProspect
from app.models.prospect_signal import ProspectSignalType
from app.services.scraping.website_scraper import (
    WebsiteScraperError,
    WebsiteScraperService,
)
from app.services.signals.protocol import BaseSignalProvider
from app.services.signals.types import CollectedSignal

# Human-readable labels + per-pixel weights for the strength blend.
_PIXEL_LABELS: dict[str, str] = {
    "meta_pixel": "Meta Pixel",
    "google_ads": "Google Ads",
    "google_analytics": "Google Analytics",
    "gtm": "Google Tag Manager",
    "linkedin_pixel": "LinkedIn Insight",
    "tiktok_pixel": "TikTok Pixel",
}
# Ad pixels (intent to advertise) weigh more than pure analytics.
_PIXEL_WEIGHTS: dict[str, int] = {
    "meta_pixel": 35,
    "google_ads": 35,
    "tiktok_pixel": 25,
    "linkedin_pixel": 20,
    "gtm": 10,
    "google_analytics": 10,
}


def signal_from_pixels(pixels: dict[str, bool]) -> CollectedSignal | None:
    """Map detected ad/analytics pixels into an ``ad_tech`` signal (pure).

    Returns ``None`` when no relevant pixel is present.
    """
    detected = [name for name, present in pixels.items() if present and name in _PIXEL_WEIGHTS]
    if not detected:
        return None

    strength = min(100, sum(_PIXEL_WEIGHTS[name] for name in detected))
    labels = [_PIXEL_LABELS.get(name, name) for name in detected]
    has_ad_pixel = any(name in ("meta_pixel", "google_ads", "tiktok_pixel") for name in detected)
    summary = (
        f"Running ad-tech: {', '.join(labels)} installed."
        if has_ad_pixel
        else f"Analytics installed: {', '.join(labels)}."
    )
    return CollectedSignal(
        signal_type=ProspectSignalType.AD_TECH.value,
        strength=strength,
        source="website",
        summary=summary,
        payload={
            "pixels": detected,
            "labels": labels,
            "has_ad_pixel": has_ad_pixel,
        },
    )


class AdTechSignalProvider(BaseSignalProvider):
    """Emit an ``ad_tech`` signal from the prospect site's installed pixels."""

    signal_source: ClassVar[str] = "website"

    def __init__(
        self,
        scraper: WebsiteScraperService | None = None,
        *,
        pixels: dict[str, bool] | None = None,
    ) -> None:
        self._scraper = scraper
        self._owns_scraper = scraper is None
        # Pre-scraped pixels (e.g. from the enrichment worker) short-circuit I/O.
        self._pixels = pixels

    async def collect(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        pixels = self._pixels
        if pixels is None:
            pixels = await self._detect(prospect)
        if not pixels:
            return []
        signal = signal_from_pixels(pixels)
        return [signal] if signal is not None else []

    async def _detect(self, prospect: LeadProspect) -> dict[str, bool] | None:
        url = prospect.website_url or prospect.website_host
        if not url:
            return None
        scraper = self._scraper or WebsiteScraperService()
        try:
            result = await scraper.scrape_website(url)
        except WebsiteScraperError:
            return None
        finally:
            if self._owns_scraper and self._scraper is None:
                await scraper.close()
        pixels = result.get("ad_pixels")
        return pixels if isinstance(pixels, dict) else None
