"""Tests for the in-house Meta self-scrape provider.

All Facebook traffic is faked through an ``httpx.MockTransport`` (mirroring
``test_meta_ad_library_provider.py``) so no real network egress leaves the test
runner. Covers: LSD/DTSG-token bootstrap from the Ad Library page HTML, the
``/api/graphql/`` persisted-query request shape (``doc_id`` + URL-encoded
``variables`` + ``fb_api_req_friendly_name``), page-name typeahead resolution,
normalization parity with the shared internal-shape normalizer, cursor
pagination via the GraphQL ``page_info.end_cursor``, a single 403 ->
re-bootstrap self-heal, the hard compliance-gate raise, and a regression guard
that the provider never POSTs the retired ``async/search_ads/`` endpoint.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.services.ad_intelligence import compliance
from app.services.ad_intelligence.errors import AdLibraryProviderUnavailableError
from app.services.ad_intelligence.providers import meta_scraper
from app.services.ad_intelligence.providers._meta_internal_shape import normalize_ad
from app.services.ad_intelligence.providers.meta_scraper import MetaScraperProvider
from app.services.ad_intelligence.scraper_session import (
    GRAPHQL_URL,
    HeadlessSession,
    TokenHttpSession,
    build_session,
    decode_graphql_payload,
    extract_dtsg,
    extract_lsd,
)
from app.services.ad_intelligence.types import AdSearchRequest
from app.services.lead_discovery.errors import (
    LeadDiscoveryAuthError,
    LeadDiscoveryProviderError,
)

_FIXTURES = Path(__file__).parent / "fixtures"
# HTML stub carrying both an LSD token (primary shape) and an fb_dtsg token.
_PAGE_HTML = (
    '<!doctype html><html><script>["LSD",[],{"token":"lsd-token-abc123"}],'
    '["DTSGInitialData",[],{"token":"dtsg-token-abc123"}]</script></html>'
)
_PAGE_HTML_B = (
    '<!doctype html><html><script>["LSD",[],{"token":"lsd-token-xyz789"}],'
    '["DTSGInitialData",[],{"token":"dtsg-token-xyz789"}]</script></html>'
)


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())


def _variables(body: dict[str, list[str]]) -> dict[str, Any]:
    """Decode the URL-encoded ``variables`` JSON blob out of a posted form."""
    return json.loads(body["variables"][0])


class _FakeRedis:
    """No-op Redis double: forces a fresh bootstrap, accepts cache writes."""

    async def get(self, _key: str) -> None:
        return None

    async def setex(self, _key: str, _ttl: int, _value: str) -> None:
        return None

    async def delete(self, _key: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _enable_scrape(monkeypatch) -> None:
    """Default every test to the 'scraping allowed + slot granted' happy path.

    Individual tests override the compliance flag to exercise the gate.
    """
    monkeypatch.setattr(compliance.settings, "ad_library_allow_raw_scrape", True, raising=False)
    monkeypatch.setattr(settings, "meta_scrape_search_doc_id", "DOCID_SEARCH", raising=False)
    monkeypatch.setattr(settings, "meta_scrape_typeahead_doc_id", "DOCID_TYPEAHEAD", raising=False)

    async def _allow() -> tuple[bool, int]:
        return True, 1

    monkeypatch.setattr(meta_scraper, "acquire_scrape_call_slot", _allow)

    async def _fake_redis() -> _FakeRedis:
        return _FakeRedis()

    # The session caches the token/cookies in Redis; fake it so no server is hit.
    monkeypatch.setattr("app.services.ad_intelligence.scraper_session.get_redis", _fake_redis)


def _provider(handler) -> MetaScraperProvider:  # noqa: ANN001
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    session = TokenHttpSession(client=client, proxy_url="")
    # Zero pacing so the test never really sleeps between pages.
    return MetaScraperProvider(session=session, min_delay_seconds=0, max_delay_seconds=0)


@pytest.mark.asyncio
async def test_graphql_bootstrap_and_request_shape_and_paginate() -> None:
    calls: dict[str, int] = {"page": 0, "graphql": 0}
    bodies: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            calls["page"] += 1
            return httpx.Response(200, text=_PAGE_HTML)
        if str(request.url) == GRAPHQL_URL:
            calls["graphql"] += 1
            bodies.append(parse_qs(request.content.decode(), keep_blank_values=True))
            page = _load(
                "meta_graphql_search_page1.json"
                if calls["graphql"] == 1
                else "meta_graphql_search_page2.json"
            )
            return httpx.Response(200, text=json.dumps(page))
        return httpx.Response(404)

    provider = _provider(handler)
    result = await provider.search(
        AdSearchRequest(
            platform="meta", country="us", search_terms="roofing contractors", max_results=50
        )
    )
    await provider.close()

    # Bootstrapped once, then followed the GraphQL cursor to a second page.
    assert calls["page"] == 1
    assert calls["graphql"] == 2
    # Persisted-query request shape: friendly name + doc_id + LSD/DTSG tokens.
    first = bodies[0]
    assert first["fb_api_req_friendly_name"] == ["AdLibrarySearchPaginationQuery"]
    assert first["doc_id"] == ["DOCID_SEARCH"]
    assert first["lsd"] == ["lsd-token-abc123"]
    assert first["fb_dtsg"] == ["dtsg-token-abc123"]
    # The query lives in the URL-encoded ``variables`` JSON blob, not a form field.
    variables = _variables(first)
    assert variables["queryString"] == "roofing contractors"
    assert variables["countries"] == ["US"]  # country upper-cased
    assert variables["searchType"] == "keyword_unordered"
    assert variables["activeStatus"] == "all"
    # One advertiser (same page id) carrying all three ads across both pages.
    assert result.advertiser_count == 1
    advertiser = result.advertisers[0]
    assert advertiser.advertiser_key == "1122334455"
    assert advertiser.advertiser_name == "Apex Roofing Co"
    assert advertiser.ad_count == 3
    assert advertiser.website_host == "apexroofing.com"


@pytest.mark.asyncio
async def test_pagination_advances_graphql_cursor() -> None:
    bodies: list[dict[str, list[str]]] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            return httpx.Response(200, text=_PAGE_HTML)
        if str(request.url) == GRAPHQL_URL:
            calls["n"] += 1
            bodies.append(parse_qs(request.content.decode(), keep_blank_values=True))
            page = _load(
                "meta_graphql_search_page1.json"
                if calls["n"] == 1
                else "meta_graphql_search_page2.json"
            )
            return httpx.Response(200, text=json.dumps(page))
        return httpx.Response(404)

    provider = _provider(handler)
    await provider.search(
        AdSearchRequest(platform="meta", country="US", search_terms="x", max_results=60)
    )
    await provider.close()

    # First page sends a null cursor; the second carries page1's end_cursor.
    expected_cursor = _load("meta_graphql_search_page1.json")["data"]["ad_library_main"][
        "search_results_connection"
    ]["page_info"]["end_cursor"]
    assert _variables(bodies[0])["cursor"] is None
    assert _variables(bodies[1])["cursor"] == expected_cursor
    # The collation token is stable across pages.
    assert _variables(bodies[0])["collationToken"] == _variables(bodies[1])["collationToken"]


@pytest.mark.asyncio
async def test_does_not_post_retired_async_endpoint() -> None:
    """Regression: the provider must never hit the retired async/search_ads/ path."""
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/ads/library/":
            return httpx.Response(200, text=_PAGE_HTML)
        if str(request.url) == GRAPHQL_URL:
            return httpx.Response(200, text=json.dumps(_load("meta_graphql_search_page2.json")))
        # The retired endpoints 404 against live Meta — fail loudly if hit.
        return httpx.Response(404)

    provider = _provider(handler)
    await provider.search(
        AdSearchRequest(platform="meta", country="US", search_terms="roofing", max_results=10)
    )
    await provider.close()

    assert not any(p.endswith("/async/search_ads/") for p in seen_paths)
    assert not any(p.endswith("/async/search_typeahead/") for p in seen_paths)
    assert "/api/graphql/" in seen_paths


@pytest.mark.asyncio
async def test_normalization_parity_with_shared_normalizer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            return httpx.Response(200, text=_PAGE_HTML)
        if str(request.url) == GRAPHQL_URL:
            return httpx.Response(200, text=json.dumps(_load("meta_graphql_search_page2.json")))
        return httpx.Response(404)

    provider = _provider(handler)
    result = await provider.search(
        AdSearchRequest(platform="meta", country="US", search_terms="x", max_results=10)
    )
    await provider.close()

    # The provider must emit exactly what the shared internal-shape normalizer
    # produces for the same raw ad node (no scraper-local drift).
    raw_ad = _load("meta_graphql_search_page2.json")["data"]["ad_library_main"][
        "search_results_connection"
    ]["edges"][0]["node"]["collated_results"][0]
    expected = normalize_ad(raw_ad)
    got = result.advertisers[0].ads[0]
    assert got == expected
    assert got.media_type == "video"
    assert got.is_active is False
    assert got.link_host == "apexroofing.com"


@pytest.mark.asyncio
async def test_typeahead_resolves_page_name() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            return httpx.Response(200, text=_PAGE_HTML)
        if str(request.url) == GRAPHQL_URL:
            body = parse_qs(request.content.decode(), keep_blank_values=True)
            friendly = body["fb_api_req_friendly_name"][0]
            if friendly == "useAdLibraryTypeaheadSuggestionDataSourceQuery":
                seen["typeahead_query"] = _variables(body)["queryString"]
                seen["typeahead_doc_id"] = body["doc_id"]
                return httpx.Response(
                    200,
                    text=json.dumps(
                        {
                            "data": {
                                "ad_library_page_typeahead": {
                                    "page_results": [
                                        {"page_id": "1122334455", "name": "Apex Roofing Co"}
                                    ]
                                }
                            }
                        }
                    ),
                )
            seen["search_variables"] = _variables(body)
            return httpx.Response(200, text=json.dumps(_load("meta_graphql_search_page2.json")))
        return httpx.Response(404)

    provider = _provider(handler)
    result = await provider.search(
        AdSearchRequest(platform="meta", country="US", page_name="Apex Roofing Co")
    )
    await provider.close()

    assert seen["typeahead_query"] == "Apex Roofing Co"
    assert seen["typeahead_doc_id"] == ["DOCID_TYPEAHEAD"]
    # The resolved numeric id scopes the subsequent search to that page.
    assert seen["search_variables"]["pageIDs"] == ["1122334455"]
    assert seen["search_variables"]["viewAllPageID"] == "1122334455"
    assert seen["search_variables"]["searchType"] == "page"
    assert result.advertisers[0].advertiser_key == "1122334455"


@pytest.mark.asyncio
async def test_403_rebootstraps_once_then_succeeds() -> None:
    calls = {"page": 0, "graphql": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            calls["page"] += 1
            # Serve a different token after re-bootstrap to prove a refresh.
            return httpx.Response(200, text=_PAGE_HTML if calls["page"] == 1 else _PAGE_HTML_B)
        if str(request.url) == GRAPHQL_URL:
            calls["graphql"] += 1
            if calls["graphql"] == 1:
                return httpx.Response(403, text="login required")
            body = parse_qs(request.content.decode(), keep_blank_values=True)
            # The retry must carry the freshly bootstrapped token.
            assert body["lsd"] == ["lsd-token-xyz789"]
            return httpx.Response(200, text=json.dumps(_load("meta_graphql_search_page2.json")))
        return httpx.Response(404)

    provider = _provider(handler)
    result = await provider.search(
        AdSearchRequest(platform="meta", country="US", search_terms="x", max_results=10)
    )
    await provider.close()

    assert calls["page"] == 2  # bootstrapped, then re-bootstrapped on the 403
    assert calls["graphql"] == 2  # original (403) + retry (200)
    assert result.advertiser_count == 1


@pytest.mark.asyncio
async def test_persistent_403_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ads/library/":
            return httpx.Response(200, text=_PAGE_HTML)
        return httpx.Response(403, text="blocked")

    provider = _provider(handler)
    with pytest.raises(LeadDiscoveryAuthError):
        await provider.search(
            AdSearchRequest(platform="meta", country="US", search_terms="x", max_results=10)
        )
    await provider.close()


# ---------------------------------------------------------------------------
# Pure session-layer helpers (no transport)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '["LSD",[],{"token":"tok_a"}]',
        '"LSD",[],{"token":"tok_a"}',
        '<input type="hidden" name="lsd" value="tok_a" />',
        '"lsd":{"token":"tok_a"}',
    ],
)
def test_extract_lsd_handles_token_shapes(html: str) -> None:
    assert extract_lsd(html) == "tok_a"


def test_extract_lsd_returns_none_when_absent() -> None:
    assert extract_lsd("<html>no token here</html>") is None


@pytest.mark.parametrize(
    "html",
    [
        '["DTSGInitialData",[],{"token":"dt_a"}]',
        '"DTSGInitData",[],{"token":"dt_a"',
        '<input type="hidden" name="fb_dtsg" value="dt_a" />',
    ],
)
def test_extract_dtsg_handles_token_shapes(html: str) -> None:
    assert extract_dtsg(html) == "dt_a"


def test_decode_graphql_payload_parses_plain_json() -> None:
    decoded = decode_graphql_payload('{"data": {"ad_library_main": {}}}')
    assert decoded == {"data": {"ad_library_main": {}}}


def test_decode_graphql_payload_strips_guard() -> None:
    decoded = decode_graphql_payload('for (;;);{"data": {"x": 1}}')
    assert decoded == {"data": {"x": 1}}


def test_decode_graphql_payload_rejects_non_json() -> None:
    # A login/challenge HTML page (no JSON) must surface as a provider error.
    with pytest.raises(LeadDiscoveryProviderError):
        decode_graphql_payload("<!doctype html><html>login</html>")


def test_decode_graphql_payload_rejects_errors_envelope() -> None:
    with pytest.raises(LeadDiscoveryProviderError):
        decode_graphql_payload('{"data": null, "errors": [{"message": "boom"}]}')


def test_build_session_selects_strategy() -> None:
    assert isinstance(build_session(strategy="token_http"), TokenHttpSession)
    assert isinstance(build_session(strategy="headless"), HeadlessSession)
    # Unknown strategy falls back to the browser-free default.
    assert isinstance(build_session(strategy="bogus"), TokenHttpSession)


@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is not None,
    reason="playwright is installed; the missing-dependency path cannot be exercised",
)
@pytest.mark.asyncio
async def test_headless_session_missing_playwright_raises() -> None:
    # Playwright is an optional heavy dep; absent it, the headless path must
    # fail with a clear, actionable provider error (not an ImportError).
    session = HeadlessSession()
    with pytest.raises(LeadDiscoveryProviderError, match="playwright"):
        await session.graphql("AdLibrarySearchPaginationQuery", "DOCID", {"queryString": "x"})
    await session.close()


@pytest.mark.asyncio
async def test_compliance_gate_raises_when_flag_off(monkeypatch) -> None:
    monkeypatch.setattr(compliance.settings, "ad_library_allow_raw_scrape", False, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        return httpx.Response(200, text=_PAGE_HTML)

    provider = _provider(handler)
    with pytest.raises(AdLibraryProviderUnavailableError):
        await provider.search(AdSearchRequest(platform="meta", country="US", search_terms="x"))
    await provider.close()
