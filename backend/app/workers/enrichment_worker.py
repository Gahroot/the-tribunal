"""Enrichment worker service for processing contact website scraping.

This background worker:
1. Polls for contacts with enrichment_status = "pending" and website_url IS NOT NULL
2. Scrapes website for social media links and metadata
3. Updates contact with linkedin_url, business_intel, enrichment_status
4. Handles errors gracefully with status tracking
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.contact import Contact
from app.services.scraping.ai_content_analyzer import AIContentAnalyzerService
from app.services.scraping.website_scraper import WebsiteScraperError, WebsiteScraperService

logger = structlog.get_logger()

# Worker configuration
POLL_INTERVAL_SECONDS = getattr(settings, "enrichment_poll_interval", 30)
MAX_CONTACTS_PER_TICK = 10


class EnrichmentWorker:
    """Background worker for enriching contacts with website data."""

    def __init__(self) -> None:
        """Initialize the enrichment worker."""
        self.running = False
        self.logger = logger.bind(component="enrichment_worker")
        self._task: asyncio.Task[None] | None = None
        self._scraper: WebsiteScraperService | None = None
        self._ai_analyzer: AIContentAnalyzerService | None = None

    async def start(self) -> None:
        """Start the enrichment worker background task."""
        if self.running:
            self.logger.warning("Enrichment worker already running")
            return

        self.running = True
        self._scraper = WebsiteScraperService()
        if settings.enable_ai_enrichment:
            self._ai_analyzer = AIContentAnalyzerService()
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("Enrichment worker started")

    async def stop(self) -> None:
        """Stop the enrichment worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._scraper:
            await self._scraper.close()
            self._scraper = None
        self._ai_analyzer = None
        self.logger.info("Enrichment worker stopped")

    async def _run_loop(self) -> None:
        """Main worker loop that polls for contacts to enrich."""
        while self.running:
            try:
                await self._process_pending_contacts()
            except Exception:
                self.logger.exception("Error in enrichment worker loop")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _process_pending_contacts(self) -> None:
        """Process all pending contacts for enrichment."""
        async with AsyncSessionLocal() as db:
            # Find contacts with pending enrichment that have a website
            result = await db.execute(
                select(Contact)
                .where(
                    and_(
                        Contact.enrichment_status == "pending",
                        Contact.website_url.isnot(None),
                        Contact.website_url != "",
                    )
                )
                .limit(MAX_CONTACTS_PER_TICK)
                .with_for_update(skip_locked=True)
            )
            contacts = result.scalars().all()

            if not contacts:
                return

            self.logger.debug("Processing pending enrichments", count=len(contacts))

            for contact in contacts:
                try:
                    await self._enrich_contact(contact, db)
                except Exception:
                    self.logger.exception(
                        "Error enriching contact",
                        contact_id=contact.id,
                    )

            await db.commit()

    async def _enrich_contact(self, contact: Contact, db: AsyncSession) -> None:
        """Enrich a single contact with website data.

        Args:
            contact: Contact to enrich
            db: Database session
        """
        log = self.logger.bind(
            contact_id=contact.id,
            website_url=contact.website_url,
        )

        if not self._scraper:
            log.error("Scraper not initialized")
            return

        if not contact.website_url:
            contact.enrichment_status = "skipped"
            log.debug("No website URL, skipping")
            return

        try:
            log.info("Starting website enrichment")

            # Scrape website
            result = await self._scraper.scrape_website(contact.website_url)

            # Extract data
            social_links: dict[str, Any] = result.get("social_links", {})
            website_meta: dict[str, Any] = result.get("website_meta", {})

            # Update linkedin_url if found
            if social_links.get("linkedin"):
                contact.linkedin_url = social_links["linkedin"]

            # Build business_intel JSONB
            business_intel: dict[str, Any] = contact.business_intel or {}
            business_intel["social_links"] = social_links
            business_intel["website_meta"] = website_meta

            # Generate AI website summary if enabled
            html_content = result.get("html_content")
            if self._ai_analyzer and html_content:
                website_summary = await self._ai_analyzer.generate_website_summary(
                    html_content=html_content,
                    website_url=contact.website_url,
                    business_name=contact.company_name,
                )
                if website_summary:
                    business_intel["website_summary"] = website_summary.model_dump()

            contact.business_intel = business_intel

            # Update status
            contact.enrichment_status = "enriched"
            contact.enriched_at = datetime.now(UTC)

            log.info(
                "Contact enriched successfully",
                linkedin_found=bool(social_links.get("linkedin")),
                social_count=sum(1 for v in social_links.values() if v),
            )

        except WebsiteScraperError as e:
            log.warning("Website scraping failed", error=str(e))

            # Store error in business_intel
            business_intel = contact.business_intel or {}
            business_intel["enrichment_error"] = str(e)
            business_intel["enrichment_failed_at"] = datetime.now(UTC).isoformat()
            contact.business_intel = business_intel

            contact.enrichment_status = "failed"

        except Exception as e:
            log.exception("Unexpected enrichment error", error=str(e))

            business_intel = contact.business_intel or {}
            business_intel["enrichment_error"] = f"Unexpected error: {e}"
            business_intel["enrichment_failed_at"] = datetime.now(UTC).isoformat()
            contact.business_intel = business_intel

            contact.enrichment_status = "failed"


# Global worker instance
_enrichment_worker: EnrichmentWorker | None = None


async def start_enrichment_worker() -> EnrichmentWorker:
    """Start the global enrichment worker."""
    global _enrichment_worker
    if _enrichment_worker is None:
        _enrichment_worker = EnrichmentWorker()
        await _enrichment_worker.start()
    return _enrichment_worker


async def stop_enrichment_worker() -> None:
    """Stop the global enrichment worker."""
    global _enrichment_worker
    if _enrichment_worker:
        await _enrichment_worker.stop()
        _enrichment_worker = None


def get_enrichment_worker() -> EnrichmentWorker | None:
    """Get the global enrichment worker instance."""
    return _enrichment_worker
