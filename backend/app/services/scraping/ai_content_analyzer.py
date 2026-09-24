"""AI-powered website content analyzer for lead enrichment."""

import asyncio

import structlog
from bs4 import BeautifulSoup
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.schemas.find_leads_ai import WebsiteSummary
from app.services.ai.openai_credentials import get_openai_bearer_token
from app.services.ai.structured_output import generate_structured

logger = structlog.get_logger()


class _WebsiteAnalysis(WebsiteSummary):
    business_description: str | None
    services: list[str]
    target_market: str | None
    unique_selling_points: list[str]
    industry: str | None
    team_size_estimate: str
    years_in_business: int | None
    service_areas: list[str]
    revenue_signals: list[str]
    has_financing: bool
    certifications: list[str]
    decision_maker_name: str | None
    decision_maker_title: str | None


WEBSITE_ANALYSIS_PROMPT = """Analyze this business website content and extract key information.

Return ONLY valid JSON with this structure:
{
    "business_description": "What the business does (1-2 sentences)",
    "services": ["Service 1", "Service 2", ...],  // Up to 5 main services
    "target_market": "Who they serve",
    "unique_selling_points": ["USP 1", "USP 2"],  // Up to 3
    "industry": "Industry category",
    "team_size_estimate": "solo | small (2-5) | medium (6-20) | large (20+) | unknown",
    "years_in_business": null,  // number or null
    "service_areas": ["City 1", "City 2"],  // Up to 10
    "revenue_signals": ["fleet of 10 trucks", "5000+ projects completed"],  // Scale indicators
    "has_financing": false,  // Whether they offer financing options
    "certifications": ["GAF Master Elite", "BBB A+"],  // Industry certifications or accreditations
    "decision_maker_name": null,  // Owner/Founder/CEO name if found on About/Team page
    "decision_maker_title": null  // Their title (Owner, Founder, CEO, President, etc.)
}

If information is not available, use null for strings/numbers or empty arrays for lists.
For team_size_estimate, look for "our team", staff photos, about pages, employee counts.
For revenue_signals, look for fleet sizes, project counts, years in business, service area breadth.
For has_financing, look for "financing available", "payment plans", "0% APR", etc.
For decision_maker_name, look for owner names, founder names, CEO/President
on "About Us", "Our Team", "Meet the Team" pages.
Look for patterns like "Founded by [Name]", "[Name], Owner", "Meet [Name]".
Only include if clearly identified.
For decision_maker_title, extract their title/role
(Owner, Founder, CEO, President, Managing Partner, etc.)"""


class AIContentAnalyzerService:
    """Service for AI-powered website content analysis."""

    def __init__(self, api_key: str | None = None) -> None:
        self._openai = AsyncOpenAI(api_key=api_key or get_openai_bearer_token())
        self.logger = logger.bind(component="ai_content_analyzer")

    def _extract_text(self, html: str, max_chars: int = 8000) -> str:
        """Extract readable text from HTML, truncated for token limits."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = " ".join(text.split())
        return text[:max_chars]

    async def generate_website_summary(
        self,
        html_content: str,
        website_url: str,
        business_name: str | None = None,
    ) -> WebsiteSummary | None:
        """Generate AI summary of website content.

        Args:
            html_content: Raw HTML from website
            website_url: URL for context
            business_name: Optional business name for context

        Returns:
            WebsiteSummary or None if analysis fails
        """
        log = self.logger.bind(website_url=website_url)

        text_content = self._extract_text(html_content)
        if len(text_content) < 100:
            log.warning("insufficient_content", text_length=len(text_content))
            return None

        context = (
            f"Business: {business_name}\nWebsite: {website_url}\n\n"
            if business_name
            else f"Website: {website_url}\n\n"
        )

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                result = await generate_structured(
                    client=self._openai,
                    model="gpt-5.4-nano",
                    schema=_WebsiteAnalysis,
                    system_prompt=WEBSITE_ANALYSIS_PROMPT,
                    user_prompt=context + text_content,
                    temperature=0.3,
                    max_tokens=800,
                    timeout=30.0,
                )
                log.info(
                    "website_summary_generated",
                    has_description=bool(result.business_description),
                )
                return WebsiteSummary.model_validate(
                    {
                        **result.model_dump(),
                        "services": result.services[:5],
                        "unique_selling_points": result.unique_selling_points[:3],
                        "service_areas": result.service_areas[:10],
                        "revenue_signals": result.revenue_signals[:5],
                        "certifications": result.certifications[:10],
                    }
                )

            except RateLimitError as e:
                if attempt < max_retries - 1:
                    log.warning(
                        "openai_rate_limit",
                        attempt=attempt + 1,
                        backoff=backoff,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                log.warning("openai_rate_limit_max_retries", error=str(e))
                raise

            except (APIConnectionError, APITimeoutError, TimeoutError) as e:
                if attempt < max_retries - 1:
                    log.warning(
                        "openai_transient_error",
                        attempt=attempt + 1,
                        backoff=backoff,
                        error_type=type(e).__name__,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                log.warning(
                    "openai_transient_error_max_retries",
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise

            except Exception:
                log.exception("website_summary_failed")
                raise

        return None
