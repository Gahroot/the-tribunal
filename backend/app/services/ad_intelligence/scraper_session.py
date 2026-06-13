"""Token/cookie session layer for self-scraping the public Ad Library.

The public Ad Library website is powered by Meta's internal GraphQL endpoint
``POST https://www.facebook.com/api/graphql/``. It is driven with **persisted
queries**: the client sends a Relay ``doc_id`` plus a URL-encoded ``variables``
JSON blob and a ``fb_api_req_friendly_name``, authenticated with an **LSD CSRF
token** (and, when present, ``fb_dtsg``) plus the session cookies the website
sets. We harvest those tokens by loading the Ad Library page once and reusing
them across calls within a short TTL budget.

.. note::
   Meta retired the older ``POST .../ads/library/async/search_ads/`` (and the
   sibling ``async/search_typeahead/``) form endpoints — both now return HTTP
   404. This module targets ``/api/graphql/`` instead.

Two interchangeable strategies implement :class:`ScrapeSession`:

* :class:`TokenHttpSession` — lightweight, no browser. GETs the Ad Library page
  over ``httpx``, regexes the LSD/DTSG tokens out of the HTML, keeps the cookie
  jar, and POSTs ``/api/graphql/`` reusing them. Cheapest; most brittle.
  **Cannot** clear the initial HTTP 403 JS challenge (it can't run JS), so it is
  unsuitable for live scraping today — kept for tests/DI and future use. Caches
  the harvested token+cookies in Redis (shared across replicas) with
  ``meta_scrape_session_ttl_seconds`` TTL and re-bootstraps once on 401/403.
* :class:`HeadlessSession` — heavier, lazily imported. Drives Playwright
  Chromium to the Ad Library page (a real browser transparently clears the JS
  challenge and produces valid tokens + a browser-grade TLS fingerprint),
  extracts the LSD/DTSG tokens, then issues the GraphQL POSTs through the
  browser context's request API so cookies + fingerprint are reused. **Required**
  for live scraping; needs the optional ``playwright`` dependency.

Neither session decides *policy*: the compliance gate and rate limiting live in
the provider. This module only owns the token/cookie/transport lifecycle and the
GraphQL envelope decoding.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable
from urllib.parse import parse_qsl

import httpx
import structlog

from app.core.config import settings
from app.db.redis import get_redis
from app.services.lead_discovery.errors import (
    LeadDiscoveryAuthError,
    LeadDiscoveryProviderError,
    LeadDiscoveryRateLimitError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

logger = structlog.get_logger()

AD_LIBRARY_URL = "https://www.facebook.com/ads/library/"
# The current internal endpoint the Ad Library website posts persisted GraphQL
# queries to. (The retired ``.../ads/library/async/*`` endpoints 404.)
GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
# A current, desktop Chrome UA. The endpoint rejects obviously-bot UAs.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SESSION_CACHE_KEY = "ad_library:scrape:session"

# LSD CSRF token shapes seen in the Ad Library HTML, most specific first.
_LSD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\["LSD",\[\],\{"token":"([^"]+)"\}'),
    re.compile(r'"LSD",\[\],\{"token":"([^"]+)"\}'),
    re.compile(r'name="lsd"\s+value="([^"]+)"'),
    re.compile(r'"lsd":\{"token":"([^"]+)"\}'),
)
# ``fb_dtsg`` token shapes (used by GraphQL writes; harmless to send on reads).
_DTSG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\["DTSGInitialData",\[\],\{"token":"([^"]+)"\}'),
    re.compile(r'"DTSGInitData",\[\],\{"token":"([^"]+)"'),
    re.compile(r'name="fb_dtsg"\s+value="([^"]+)"'),
)
# Leading anti-JSON-hijacking guard Meta sometimes prepends to JSON responses.
_FOR_LOOP_GUARD = re.compile(r"^\s*for\s*\(\s*;\s*;\s*\)\s*;")


# ---------------------------------------------------------------------------
# Pure envelope helpers (shared by both strategies; trivially unit-testable)
# ---------------------------------------------------------------------------


def extract_lsd(html: str) -> str | None:
    """Pull the LSD CSRF token out of the Ad Library page HTML, if present."""
    for pattern in _LSD_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


def extract_dtsg(html: str) -> str | None:
    """Pull the ``fb_dtsg`` token out of the Ad Library page HTML, if present."""
    for pattern in _DTSG_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


def decode_graphql_payload(text: str) -> dict[str, Any]:
    """Decode the ``/api/graphql/`` JSON envelope.

    Strips the optional ``for (;;);`` anti-hijacking guard, then parses the
    first JSON object (the endpoint can emit newline-delimited ``@defer``/
    ``@stream`` chunks; the Ad Library query returns a single object).

    Raises:
        LeadDiscoveryProviderError: when the body is not valid JSON (markup /
            anti-bot HTML / JS challenge page instead of JSON) or carries a
            GraphQL ``errors`` envelope.
    """
    stripped = _FOR_LOOP_GUARD.sub("", text, count=1).strip()
    decoded: Any = None
    if stripped:
        first_line = stripped.split("\n", 1)[0].strip()
        for candidate in (first_line, stripped):
            try:
                decoded = json.loads(candidate)
                break
            except ValueError:
                decoded = None
    if decoded is None:
        raise LeadDiscoveryProviderError(
            "Ad Library GraphQL endpoint returned a non-JSON body "
            "(likely a login or JS-challenge page; the headless strategy is required)"
        )
    if not isinstance(decoded, dict):
        raise LeadDiscoveryProviderError("Ad Library GraphQL endpoint returned an unexpected shape")
    errors = decoded.get("errors")
    if errors and not decoded.get("data"):
        message = ""
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            message = str(errors[0].get("message") or "")
        raise LeadDiscoveryProviderError(
            f"Ad Library GraphQL endpoint returned errors: {message or 'unknown'}"
        )
    return decoded


@runtime_checkable
class ScrapeSession(Protocol):
    """Transport that POSTs the Ad Library GraphQL endpoint with a live token."""

    async def graphql(
        self, friendly_name: str, doc_id: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST a persisted GraphQL query and return the decoded JSON envelope.

        Implementations inject the LSD (+ ``fb_dtsg``) tokens, URL-encode the
        ``variables`` JSON blob and ``doc_id``, attach the harvested cookies,
        and map transport failures to the discovery error hierarchy (401/403 ->
        auth, 429 -> rate-limit).
        """
        ...

    async def close(self) -> None:
        """Release any pooled resources (HTTP clients, browsers)."""
        ...


def _graphql_body(
    *,
    friendly_name: str,
    doc_id: str,
    variables: Mapping[str, Any],
    lsd: str,
    dtsg: str | None,
) -> dict[str, str]:
    """Build the form body the Ad Library website posts to ``/api/graphql/``."""
    body: dict[str, str] = {
        "av": "0",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "dpr": "1",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "variables": json.dumps(variables, separators=(",", ":")),
        "server_timestamps": "true",
        "doc_id": doc_id,
        "lsd": lsd,
    }
    if dtsg:
        body["fb_dtsg"] = dtsg
    return body


def _graphql_headers(*, friendly_name: str, lsd: str) -> dict[str, str]:
    return {
        "X-FB-LSD": lsd,
        "X-FB-Friendly-Name": friendly_name,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": AD_LIBRARY_URL,
        "X-Requested-With": "XMLHttpRequest",
    }


class TokenHttpSession:
    """Browser-free LSD-token + cookie GraphQL session over ``httpx``."""

    strategy: ClassVar[str] = "token_http"

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        ttl_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the token/cookie HTTP session.

        Args:
            proxy_url: Optional residential/ISP proxy URL for all egress.
            ttl_seconds: Cross-process token cache TTL (Redis).
            client: Optional injected ``httpx.AsyncClient`` (tests/DI). When
                omitted the session owns a cookie-jar-bearing client.
        """
        resolved_proxy = proxy_url if proxy_url is not None else settings.meta_scrape_proxy_url
        self._proxy_url = resolved_proxy or None
        self._ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else settings.meta_scrape_session_ttl_seconds
        )
        self._client = client
        self._owns_client = client is None
        # In-process cache of the harvested tokens (reused across paginated
        # calls within one search so we bootstrap at most once per search).
        self._lsd: str | None = None
        self._dtsg: str | None = None
        self._cookies: dict[str, str] = {}
        self._fetched_at: float = 0.0
        self._logger = logger.bind(component="meta_scrape_session", strategy=self.strategy)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.meta_ad_library_request_timeout_seconds),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                follow_redirects=True,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                proxy=self._proxy_url,
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    def _is_fresh(self) -> bool:
        return bool(self._lsd) and (time.monotonic() - self._fetched_at) < self._ttl_seconds

    async def _ensure_token(self) -> str:
        if self._is_fresh():
            return self._lsd or ""
        cached = await self._read_cache()
        if cached is not None:
            self._lsd, self._dtsg, self._cookies, self._fetched_at = cached
            return self._lsd
        return await self._bootstrap()

    async def _bootstrap(self) -> str:
        """Load the Ad Library page, harvest the LSD/DTSG tokens + cookies, cache them."""
        client = await self._get_client()
        try:
            response = await client.get(AD_LIBRARY_URL, params={"active_status": "all"})
        except httpx.TimeoutException as exc:
            raise LeadDiscoveryProviderError(f"Ad Library page load timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise LeadDiscoveryProviderError(f"Ad Library page load failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise LeadDiscoveryAuthError(
                f"Ad Library page rejected the request (status {response.status_code}); "
                "the page served a login/JS challenge — use META_SCRAPE_STRATEGY=headless"
            )
        if response.status_code != 200:
            raise LeadDiscoveryProviderError(
                f"Ad Library page load error (status {response.status_code})"
            )

        lsd = extract_lsd(response.text)
        if not lsd:
            raise LeadDiscoveryProviderError(
                "Could not extract an LSD token from the Ad Library page "
                "(markup changed or a JS-challenge page was served — the token_http "
                "strategy cannot run JS; use META_SCRAPE_STRATEGY=headless)"
            )
        self._lsd = lsd
        self._dtsg = extract_dtsg(response.text)
        self._cookies = {c.name: c.value for c in client.cookies.jar if c.value is not None}
        self._fetched_at = time.monotonic()
        await self._write_cache()
        self._logger.info("scrape_session_bootstrapped", cookie_count=len(self._cookies))
        return lsd

    async def _invalidate(self) -> None:
        self._lsd = None
        self._dtsg = None
        self._cookies = {}
        self._fetched_at = 0.0
        try:
            redis = await get_redis()
            await redis.delete(_SESSION_CACHE_KEY)
        except Exception as exc:  # noqa: BLE001 - cache is best-effort
            self._logger.debug("scrape_session_cache_clear_failed", error=type(exc).__name__)

    async def _read_cache(self) -> tuple[str, str | None, dict[str, str], float] | None:
        try:
            redis = await get_redis()
            raw = await redis.get(_SESSION_CACHE_KEY)
        except Exception as exc:  # noqa: BLE001 - fail open, bootstrap fresh
            self._logger.debug("scrape_session_cache_read_failed", error=type(exc).__name__)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            lsd = str(data["lsd"])
            dtsg_raw = data.get("dtsg")
            dtsg = str(dtsg_raw) if dtsg_raw else None
            cookies = {str(k): str(v) for k, v in dict(data.get("cookies", {})).items()}
        except (ValueError, KeyError, TypeError):
            return None
        # Re-prime the live client cookie jar so the cross-process token is usable.
        client = await self._get_client()
        for name, value in cookies.items():
            client.cookies.set(name, value, domain=".facebook.com")
        return lsd, dtsg, cookies, time.monotonic()

    async def _write_cache(self) -> None:
        try:
            redis = await get_redis()
            await redis.setex(
                _SESSION_CACHE_KEY,
                max(1, self._ttl_seconds),
                json.dumps({"lsd": self._lsd, "dtsg": self._dtsg, "cookies": self._cookies}),
            )
        except Exception as exc:  # noqa: BLE001 - cache is best-effort
            self._logger.debug("scrape_session_cache_write_failed", error=type(exc).__name__)

    # ------------------------------------------------------------------
    # GraphQL POST
    # ------------------------------------------------------------------

    async def graphql(
        self, friendly_name: str, doc_id: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST a persisted GraphQL query reusing the LSD/DTSG tokens + cookies.

        Re-bootstraps the token exactly once on a 401/403 (stale token/cookies)
        before surfacing an auth error, so a single token expiry self-heals.
        """
        await self._ensure_token()
        try:
            return await self._post_once(friendly_name, doc_id, variables)
        except LeadDiscoveryAuthError:
            # Token/cookies likely went stale mid-budget; refresh once and retry.
            self._logger.info("scrape_session_reauth", friendly_name=friendly_name)
            await self._invalidate()
            await self._bootstrap()
            return await self._post_once(friendly_name, doc_id, variables)

    async def _post_once(
        self, friendly_name: str, doc_id: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        client = await self._get_client()
        lsd = self._lsd or ""
        body = _graphql_body(
            friendly_name=friendly_name,
            doc_id=doc_id,
            variables=variables,
            lsd=lsd,
            dtsg=self._dtsg,
        )
        headers = _graphql_headers(friendly_name=friendly_name, lsd=lsd)
        try:
            response = await client.post(GRAPHQL_URL, data=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise LeadDiscoveryProviderError(
                f"Ad Library GraphQL request timed out: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise LeadDiscoveryProviderError(f"Ad Library GraphQL request failed: {exc}") from exc

        if response.status_code == 200:
            return decode_graphql_payload(response.text)
        if response.status_code == 429:
            self._logger.warning("scrape_rate_limited", status=response.status_code)
            raise LeadDiscoveryRateLimitError("Ad Library GraphQL endpoint throttled (429)")
        if response.status_code in (401, 403):
            self._logger.warning("scrape_auth_error", status=response.status_code)
            raise LeadDiscoveryAuthError(
                f"Ad Library GraphQL endpoint rejected the token (status {response.status_code})"
            )
        self._logger.warning("scrape_provider_error", status=response.status_code)
        raise LeadDiscoveryProviderError(
            f"Ad Library GraphQL endpoint error (status {response.status_code})"
        )


# A neutral keyword used only to make the page fire its own search query during
# bootstrap so we can capture a valid request-body template.
_SEED_QUERY = "marketing"
_SEED_URL = (
    f"{AD_LIBRARY_URL}?active_status=all&ad_type=all&country=US"
    f"&q={_SEED_QUERY}&search_type=keyword_unordered&media_type=all"
)


# In-page fetch executed inside the authenticated page's JS context. Posting
# from the page (vs Playwright's APIRequestContext) is what makes Meta accept the
# request: the browser attaches the matching cookies, Origin, and ``sec-fetch-*``
# headers. Returns the HTTP status + raw body so the caller can map errors.
_GRAPHQL_FETCH_JS = """async (payload) => {
  const params = new URLSearchParams();
  for (const k in payload.body) params.append(k, payload.body[k]);
  const r = await fetch('/api/graphql/', {
    method: 'POST',
    body: params,
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-fb-friendly-name': payload.friendly_name,
      'x-fb-lsd': payload.lsd,
    },
    credentials: 'include',
  });
  return { status: r.status, body: await r.text() };
}"""


class HeadlessSession:
    """Playwright-Chromium GraphQL session (lazily imported).

    Beyond ``doc_id`` / ``variables`` / ``lsd``, Meta's ``/api/graphql/`` rejects
    requests (error 1357054) unless they also carry the page's session-level
    boilerplate — ``jazoest``, ``__spin_*``, ``__rev``, ``__hs``, ``__csr``,
    ``__dyn`` and friends — which are derived from the bootstrap JS and rotate
    per session. Rather than re-deriving them, we let the page issue its own
    ``AdLibrarySearchPaginationQuery`` during bootstrap, capture that request's
    full form body as a **template**, and reuse the boilerplate for every
    subsequent call (the boilerplate is query-agnostic), swapping only
    ``fb_api_req_friendly_name`` / ``doc_id`` / ``variables`` / ``__req``.

    The POST itself is issued via ``fetch`` **inside the page's JS context**
    (not Playwright's separate request context), because Meta rejects replays
    that don't originate from the page with the right cookies/Origin/sec-fetch
    headers. The bootstrap page is therefore kept alive for the session.
    """

    strategy: ClassVar[str] = "headless"

    def __init__(self, *, proxy_url: str | None = None) -> None:
        """Initialize the headless session.

        Args:
            proxy_url: Optional residential/ISP proxy URL for the browser.
        """
        self._proxy_url = (
            proxy_url if proxy_url is not None else settings.meta_scrape_proxy_url
        ) or None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lsd: str | None = None
        # Captured request-body template (session boilerplate) reused per call.
        self._template: dict[str, str] | None = None
        self._req_counter = 0
        self._logger = logger.bind(component="meta_scrape_session", strategy=self.strategy)

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - optional heavy dep
            raise LeadDiscoveryProviderError(
                "Headless scrape strategy requires the optional 'playwright' "
                "dependency and a Chromium install (npx playwright install chromium). "
                "Use META_SCRAPE_STRATEGY=token_http for the browser-free path."
            ) from exc

        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": True}
        if self._proxy_url:
            launch_kwargs["proxy"] = {"server": self._proxy_url}
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(user_agent=DEFAULT_USER_AGENT)
        return self._context

    async def _ensure_session(self) -> dict[str, str]:
        """Bootstrap a request-body template by sniffing the page's own search call.

        Keeps the page alive afterwards so subsequent GraphQL POSTs can be issued
        from its JS context.
        """
        if self._template is not None and self._page is not None:
            return self._template
        context = await self._ensure_context()
        page = await context.new_page()
        captured: dict[str, str] = {}

        def _on_request(req: Any) -> None:
            if captured or req.method != "POST":
                return
            if not req.url.rstrip("/").endswith("/api/graphql"):
                return
            data = req.post_data or ""
            if "AdLibrarySearchPaginationQuery" in data:
                captured.update(dict(parse_qsl(data, keep_blank_values=True)))

        page.on("request", _on_request)
        # The first load returns a 403 JS challenge that POSTs ``/__rd_verify…``
        # then reloads. ``networkidle`` lets the browser clear it transparently;
        # ``domcontentloaded`` would capture the pre-reload challenge stub.
        await page.goto(_SEED_URL, wait_until="networkidle")
        html = await page.content()
        # Give the page time to fire its own search query, scrolling to nudge
        # lazy result loading if it has not fired yet.
        for _ in range(6):
            if captured:
                break
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1500)
        page.remove_listener("request", _on_request)

        lsd = captured.get("lsd") or extract_lsd(html)
        if not captured or not lsd:
            await page.close()
            raise LeadDiscoveryProviderError(
                "Headless bootstrap could not capture a valid Ad Library GraphQL "
                "request template (the JS challenge did not clear or no search "
                "query fired; check egress/UA or retry)"
            )
        self._lsd = lsd
        self._template = captured
        self._page = page
        self._logger.info(
            "scrape_session_bootstrapped", template_fields=len(captured), has_lsd=bool(lsd)
        )
        return captured

    async def graphql(
        self, friendly_name: str, doc_id: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST via in-page ``fetch`` reusing the captured body template."""
        template = await self._ensure_session()
        self._req_counter += 1
        body = dict(template)
        body["fb_api_req_friendly_name"] = friendly_name
        body["fb_api_caller_class"] = "RelayModern"
        body["doc_id"] = doc_id
        body["variables"] = json.dumps(variables, separators=(",", ":"))
        body["server_timestamps"] = "true"
        # Advance the per-request counter the way the live client does.
        body["__req"] = str(self._req_counter)
        lsd = self._lsd or template.get("lsd", "")
        payload = {"body": body, "friendly_name": friendly_name, "lsd": lsd}
        try:
            result = await self._page.evaluate(_GRAPHQL_FETCH_JS, payload)
        except Exception as exc:  # noqa: BLE001 - playwright raises broad errors
            raise LeadDiscoveryProviderError(f"Headless GraphQL request failed: {exc}") from exc

        status = int(result.get("status", 0))
        text = str(result.get("body", ""))
        if status == 200:
            return decode_graphql_payload(text)
        if status == 429:
            raise LeadDiscoveryRateLimitError("Ad Library GraphQL endpoint throttled (429)")
        if status in (401, 403):
            # Drop the session so the next call re-bootstraps a fresh template.
            await self._reset_page()
            raise LeadDiscoveryAuthError(
                f"Headless GraphQL endpoint rejected the token (status {status})"
            )
        raise LeadDiscoveryProviderError(f"Headless GraphQL endpoint error (status {status})")

    async def _reset_page(self) -> None:
        self._lsd = None
        self._template = None
        if self._page is not None:
            with contextlib.suppress(Exception):  # best-effort teardown
                await self._page.close()
            self._page = None

    async def close(self) -> None:
        if self._page is not None:
            with contextlib.suppress(Exception):  # best-effort teardown
                await self._page.close()
            self._page = None
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


def build_session(
    *,
    strategy: str | None = None,
    proxy_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> ScrapeSession:
    """Construct the configured scrape session.

    Args:
        strategy: ``token_http`` (default) or ``headless``. Falls back to
            ``meta_scrape_strategy``. Live scraping requires ``headless`` to
            clear the JS challenge.
        proxy_url: Optional residential proxy URL.
        client: Optional injected ``httpx.AsyncClient`` (token_http only).
    """
    chosen = (strategy or settings.meta_scrape_strategy or "token_http").lower()
    if chosen == "headless":
        return HeadlessSession(proxy_url=proxy_url)
    return TokenHttpSession(proxy_url=proxy_url, client=client)
