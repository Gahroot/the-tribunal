"""Shorten URLs embedded in outbound SMS for click tracking."""

import re
import secrets
import string
import uuid
from urllib.parse import urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.short_link import ShortLink

logger = structlog.get_logger()

_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_LENGTH = 7
_MAX_CODE_ATTEMPTS = 8


def _generate_short_code() -> str:
    """Generate a random 7-char base62 short code."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def _allocate_short_code(db: AsyncSession) -> str:
    """Return a short code that is not already taken in the DB."""
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = _generate_short_code()
        existing = await db.execute(
            select(ShortLink.id).where(ShortLink.short_code == code)
        )
        if existing.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Unable to allocate unique short_code after retries")


async def shorten_urls_in_text(
    body: str,
    *,
    workspace_id: uuid.UUID,
    contact_id: int | None,
    campaign_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
    db: AsyncSession,
    base_url: str,
) -> str:
    """Replace every http(s) URL in ``body`` with a tracked short link.

    URLs already pointing at our configured short domain are left alone.
    Created ShortLink rows are added to the session (caller commits).
    """
    if not body:
        return body

    base_host = urlparse(base_url).netloc.lower()
    base_url_clean = base_url.rstrip("/")

    matches = list(_URL_RE.finditer(body))
    if not matches:
        return body

    rewritten: list[str] = []
    cursor = 0
    for match in matches:
        url = match.group(0)
        rewritten.append(body[cursor : match.start()])
        cursor = match.end()

        parsed_host = urlparse(url).netloc.lower()
        if base_host and parsed_host == base_host:
            rewritten.append(url)
            continue

        code = await _allocate_short_code(db)
        short_link = ShortLink(
            workspace_id=workspace_id,
            short_code=code,
            target_url=url,
            contact_id=contact_id,
            campaign_id=campaign_id,
            message_id=message_id,
        )
        db.add(short_link)
        rewritten.append(f"{base_url_clean}/r/{code}")
        logger.info(
            "short_link_created",
            short_code=code,
            workspace_id=str(workspace_id),
            campaign_id=str(campaign_id) if campaign_id else None,
        )

    rewritten.append(body[cursor:])
    return "".join(rewritten)
