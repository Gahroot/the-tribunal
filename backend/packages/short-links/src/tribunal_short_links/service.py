"""Domain logic for the ``short-links`` block.

Two halves of the short-link lifecycle live here:

* the **write path** — :func:`shorten_urls_in_text` rewrites every ``http(s)``
  URL in an outbound SMS body into a tracked ``/r/{code}`` link, creating a
  :class:`ShortLink` row per URL. This is the block's public write API; SMS
  senders in other blocks call it instead of reaching into this block directly.
* the **read path** — :func:`record_click` resolves a code, writes a
  :class:`LinkClick` event, and bumps the per-link and per-campaign counters.

Core comes in only through ``app.core_api`` / ``app.db`` / ``app.models`` (the
shared ``Campaign`` model for the click-count bump); the block carries no
sideways import into a sibling block.
"""

from __future__ import annotations

import re
import secrets
import string
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign

from .models import LinkClick, ShortLink

logger = structlog.get_logger()

_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_LENGTH = 7
_MAX_CODE_ATTEMPTS = 8


def _generate_short_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def _insert_short_link(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    target_url: str,
    contact_id: int | None,
    campaign_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
) -> str:
    # 7-char base62 gives ~3.5T codes — collisions are astronomically rare,
    # so trust the unique index and retry only on IntegrityError.
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = _generate_short_code()
        short_link = ShortLink(
            workspace_id=workspace_id,
            short_code=code,
            target_url=target_url,
            contact_id=contact_id,
            campaign_id=campaign_id,
            message_id=message_id,
        )
        db.add(short_link)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue
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

        code = await _insert_short_link(
            db,
            workspace_id=workspace_id,
            target_url=url,
            contact_id=contact_id,
            campaign_id=campaign_id,
            message_id=message_id,
        )
        rewritten.append(f"{base_url_clean}/r/{code}")
        logger.info(
            "short_link_created",
            short_code=code,
            workspace_id=str(workspace_id),
            campaign_id=str(campaign_id) if campaign_id else None,
        )

    rewritten.append(body[cursor:])
    return "".join(rewritten)


async def record_click(
    db: AsyncSession,
    *,
    short_code: str,
    ip_address: str | None,
    user_agent: str | None,
    referer: str | None,
) -> ShortLink | None:
    """Resolve ``short_code``, log a click, and bump the counters.

    Returns the resolved :class:`ShortLink` (so the caller can redirect to its
    ``target_url``) or ``None`` when the code is unknown. Writes a
    :class:`LinkClick` event, increments ``click_count``/``last_clicked_at`` and,
    when the link is campaign-attributed, the owning campaign's
    ``links_clicked``. The transaction is committed here.
    """
    result = await db.execute(select(ShortLink).where(ShortLink.short_code == short_code))
    short_link = result.scalar_one_or_none()
    if short_link is None:
        return None

    now = datetime.now(UTC)

    click = LinkClick(
        short_link_id=short_link.id,
        clicked_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
    )
    db.add(click)

    await db.execute(
        update(ShortLink)
        .where(ShortLink.id == short_link.id)
        .values(
            click_count=ShortLink.click_count + 1,
            last_clicked_at=now,
        )
    )

    if short_link.campaign_id is not None:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == short_link.campaign_id)
            .values(links_clicked=Campaign.links_clicked + 1)
        )

    await db.commit()

    logger.info(
        "short_link_clicked",
        short_code=short_code,
        target_url=short_link.target_url,
        ip=ip_address,
    )
    return short_link
