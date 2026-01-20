"""Google Places API service for lead scraping.

Handles:
- Searching for businesses via Google Places Text Search API
- Extracting business details (name, phone, address, rating, etc.)
- Error handling and retry logic with exponential backoff
"""

import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 30


class GooglePlacesError(Exception):
    """Base exception for Google Places API errors."""

    pass


class GooglePlacesAuthError(GooglePlacesError):
    """Authentication error with Google Places API."""

    pass


class GooglePlacesRateLimitError(GooglePlacesError):
    """Rate limit exceeded on Google Places API."""

    pass


class GooglePlacesService:
    """Google Places business search service."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Google Places service.

        Args:
            api_key: Google Places API key. Falls back to settings if not provided.
        """
        self.api_key = api_key or settings.google_places_api_key
        self.base_url = "https://places.googleapis.com/v1"
        self.logger = logger.bind(component="google_places_service")
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_businesses(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for businesses using Google Places Text Search API.

        Args:
            query: Search query (e.g., "plumbers in Austin TX")
            max_results: Maximum number of results to return (default 20, max 60)

        Returns:
            List of business dictionaries with details

        Raises:
            GooglePlacesError: If API call fails
        """
        log = self.logger.bind(
            operation="search_businesses",
            query=query,
            max_results=max_results,
        )

        if not self.api_key:
            raise GooglePlacesError("Google Places API key not configured")

        try:
            client = await self.get_client()

            # Build the request payload for Text Search (New)
            payload: dict[str, Any] = {
                "textQuery": query,
                "maxResultCount": min(max_results, 20),  # API limit per request
            }

            # Field mask to request specific fields
            field_mask = ",".join([
                "places.id",
                "places.displayName",
                "places.formattedAddress",
                "places.nationalPhoneNumber",
                "places.internationalPhoneNumber",
                "places.websiteUri",
                "places.rating",
                "places.userRatingCount",
                "places.types",
                "places.businessStatus",
            ])

            log.info("searching_businesses")

            all_results: list[dict[str, Any]] = []
            next_page_token: str | None = None

            # Paginate through results
            while len(all_results) < max_results:
                if next_page_token:
                    payload["pageToken"] = next_page_token

                response = await self._request_with_retry(
                    "POST",
                    f"{self.base_url}/places:searchText",
                    json=payload,
                    headers={"X-Goog-FieldMask": field_mask},
                    client=client,
                )

                places = response.get("places", [])
                if not places:
                    break

                # Transform results
                for place in places:
                    if len(all_results) >= max_results:
                        break

                    business = self._transform_place(place)
                    all_results.append(business)

                # Check for next page
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

                # Brief delay between pagination requests
                await asyncio.sleep(0.2)

            log.info("businesses_found", count=len(all_results))
            return all_results

        except GooglePlacesError:
            raise
        except Exception as e:
            log.error("search_businesses_failed", error=str(e))
            raise GooglePlacesError(f"Failed to search businesses: {e!s}") from e

    def _transform_place(self, place: dict[str, Any]) -> dict[str, Any]:
        """Transform a Google Places result to our format.

        Args:
            place: Raw place data from Google Places API

        Returns:
            Transformed business dictionary
        """
        display_name = place.get("displayName", {})
        name = display_name.get("text", "") if isinstance(display_name, dict) else str(display_name)

        phone_number = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")
        website = place.get("websiteUri")

        return {
            "place_id": place.get("id", ""),
            "name": name,
            "address": place.get("formattedAddress", ""),
            "phone_number": phone_number,
            "website": website,
            "rating": place.get("rating"),
            "review_count": place.get("userRatingCount", 0),
            "types": place.get("types", []),
            "business_status": place.get("businessStatus", "OPERATIONAL"),
            "has_phone": bool(phone_number),
            "has_website": bool(website),
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        client: httpx.AsyncClient,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make HTTP request with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: API endpoint URL
            client: HTTP client to use
            **kwargs: Additional arguments to pass to client request

        Returns:
            JSON response from API

        Raises:
            GooglePlacesError: If all retries fail
        """
        backoff_seconds = INITIAL_BACKOFF_SECONDS

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.request(method, url, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", backoff_seconds))
                    self.logger.warning(
                        "rate_limit_hit",
                        attempt=attempt + 1,
                        retry_after=retry_after,
                    )

                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(retry_after)
                        backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
                        continue

                    raise GooglePlacesRateLimitError("Rate limit exceeded, max retries reached")

                # Handle authentication errors
                if response.status_code in {401, 403}:
                    raise GooglePlacesAuthError("Invalid API key or authentication failed")

                # Handle other HTTP errors
                if response.status_code >= 400:
                    error_msg = response.text or f"HTTP {response.status_code}"
                    self.logger.warning(
                        "http_error",
                        status_code=response.status_code,
                        error=error_msg,
                        attempt=attempt + 1,
                    )

                    if attempt < MAX_RETRIES - 1 and response.status_code >= 500:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
                        continue

                    raise GooglePlacesError(f"API error: {error_msg}")

                # Success
                return response.json()  # type: ignore[no-any-return]

            except (TimeoutError, httpx.TimeoutException) as e:
                self.logger.warning(
                    "request_timeout",
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
                    continue

                raise GooglePlacesError(f"Request timeout after {MAX_RETRIES} attempts") from e

            except (httpx.ConnectError, httpx.NetworkError) as e:
                self.logger.warning(
                    "network_error",
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, MAX_BACKOFF_SECONDS)
                    continue

                raise GooglePlacesError(f"Network error after {MAX_RETRIES} attempts") from e

        raise GooglePlacesError("Max retries exceeded")
