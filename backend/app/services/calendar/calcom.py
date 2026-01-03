"""Cal.com integration service for appointment booking and syncing.

Handles:
- Fetching available time slots from Cal.com
- Creating appointments via Cal.com API
- Syncing appointment status changes
- Error handling and retry logic with exponential backoff
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 30


class CalComError(Exception):
    """Base exception for Cal.com API errors."""

    pass


class CalComAuthError(CalComError):
    """Authentication error with Cal.com API."""

    pass


class CalComNotFoundError(CalComError):
    """Resource not found on Cal.com."""

    pass


class CalComRateLimitError(CalComError):
    """Rate limit exceeded on Cal.com API."""

    pass


class CalComService:
    """Cal.com appointment booking and sync service."""

    def __init__(self, api_key: str) -> None:
        """Initialize Cal.com service.

        Args:
            api_key: Cal.com API key for authentication
        """
        self.api_key = api_key
        self.base_url = "https://api.cal.com/v2"
        self.logger = logger.bind(component="calcom_service")
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "cal-api-version": "2024-08-13",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_availability(
        self,
        event_type_id: int,
        start_date: datetime,
        end_date: datetime,
        timezone: str = "America/New_York",
    ) -> list[dict[str, Any]]:
        """Get available slots for an event type.

        Args:
            event_type_id: Cal.com event type ID
            start_date: Start of date range for availability
            end_date: End of date range for availability
            timezone: Timezone for availability (IANA format)

        Returns:
            List of available slot dictionaries with 'date' and 'time' keys

        Raises:
            CalComError: If API call fails
        """
        log = self.logger.bind(
            operation="get_availability",
            event_type_id=event_type_id,
            timezone=timezone,
        )

        try:
            client = await self.get_client()

            # Cal.com API v2 /slots/available expects YYYY-MM-DD for startTime/endTime
            # IMPORTANT: endTime must be > startTime (at least next day) or API returns empty
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            # If same day, extend end to next day (Cal.com quirk)
            if start_str == end_str:
                next_day = end_date + timedelta(days=1)
                end_str = next_day.strftime("%Y-%m-%d")

            params = {
                "eventTypeId": event_type_id,
                "startTime": start_str,
                "endTime": end_str,
            }

            log.info(
                "fetching_availability",
                start=start_str,
                end=end_str,
            )

            response = await self._request_with_retry(
                "GET",
                f"{self.base_url}/slots/available",
                params=params,
                client=client,
            )

            # Cal.com v2 response structure:
            # {"data": {"slots": {"2024-01-15": [{"time": "2024-01-15T15:00:00.000Z"}, ...]}}}
            slots_data = response.get("data", {}).get("slots", {})

            # Convert to list of slot dicts with date and time
            slots: list[dict[str, Any]] = []
            if isinstance(slots_data, dict):
                for date_key, time_list in slots_data.items():
                    if not isinstance(time_list, list):
                        continue
                    for slot_obj in time_list:
                        # Each slot is {"time": "2024-01-15T15:00:00.000Z"}
                        if isinstance(slot_obj, dict) and "time" in slot_obj:
                            # Parse ISO time to extract date and time components
                            iso_time = slot_obj["time"]
                            # Format: "2024-01-15T15:00:00.000Z"
                            slots.append({
                                "date": date_key,
                                "time": iso_time[11:16],  # Extract "15:00" from ISO
                                "iso": iso_time,
                            })
                        elif isinstance(slot_obj, str):
                            # Fallback if it's just a time string
                            slots.append({
                                "date": date_key,
                                "time": slot_obj,
                            })

            log.info("availability_fetched", slot_count=len(slots))
            return slots

        except CalComError as e:
            log.error("get_availability_failed", error=str(e))
            raise
        except Exception as e:
            log.error("get_availability_unexpected_error", error=str(e))
            raise CalComError(f"Failed to get availability: {str(e)}") from e

    async def create_booking(
        self,
        event_type_id: int,
        contact_email: str,
        contact_name: str,
        start_time: datetime,
        duration_minutes: int = 30,
        metadata: dict[str, Any] | None = None,
        timezone: str = "America/New_York",
        language: str = "en",
        phone_number: str | None = None,
    ) -> dict[str, Any]:
        """Create an appointment booking on Cal.com.

        Args:
            event_type_id: Cal.com event type ID
            contact_email: Attendee email address
            contact_name: Attendee name
            start_time: Appointment start time (should be in UTC)
            duration_minutes: Duration in minutes (default 30)
            metadata: Optional metadata to attach to booking
            timezone: Attendee timezone in IANA format (default America/New_York)
            language: Attendee language code (default en)
            phone_number: Optional phone number for SMS reminders

        Returns:
            Booking confirmation with Cal.com IDs and details

        Raises:
            CalComError: If booking creation fails
        """
        log = self.logger.bind(
            operation="create_booking",
            event_type_id=event_type_id,
            contact_email=contact_email,
        )

        try:
            client = await self.get_client()

            # Build attendee object with required fields
            attendee: dict[str, Any] = {
                "name": contact_name,
                "email": contact_email,
                "timeZone": timezone,
                "language": language,
            }

            # Add phone number if provided (required for SMS reminders)
            if phone_number:
                attendee["phoneNumber"] = phone_number

            # Start time should be in UTC ISO format
            start_utc = start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            payload: dict[str, Any] = {
                "eventTypeId": event_type_id,
                "start": start_utc,
                "attendee": attendee,
                "metadata": metadata or {},
            }

            response = await self._request_with_retry(
                "POST",
                f"{self.base_url}/bookings",
                json=payload,
                client=client,
            )

            log.info(
                "booking_created",
                booking_id=response.get("id"),
                uid=response.get("uid"),
            )

            return response

        except CalComError as e:
            log.error("create_booking_failed", error=str(e), error_type=type(e).__name__)
            raise
        except Exception as e:
            log.error("create_booking_unexpected_error", error=str(e))
            raise CalComError(f"Failed to create booking: {str(e)}") from e

    async def get_booking(self, booking_uid: str) -> dict[str, Any]:
        """Get booking details by UID.

        Args:
            booking_uid: Cal.com booking UID (unique identifier)

        Returns:
            Booking details

        Raises:
            CalComError: If booking fetch fails
        """
        log = self.logger.bind(operation="get_booking", booking_uid=booking_uid)

        try:
            client = await self.get_client()

            response = await self._request_with_retry(
                "GET",
                f"{self.base_url}/bookings/{booking_uid}",
                client=client,
            )

            log.info("booking_fetched", booking_id=response.get("id"))
            return response

        except CalComError as e:
            log.error("get_booking_failed", error=str(e))
            raise
        except Exception as e:
            log.error("get_booking_unexpected_error", error=str(e))
            raise CalComError(f"Failed to get booking: {str(e)}") from e

    async def cancel_booking(self, booking_uid: str, reason: str = "Cancelled by customer") -> bool:
        """Cancel a booking on Cal.com.

        Args:
            booking_uid: Cal.com booking UID
            reason: Cancellation reason

        Returns:
            True if cancellation successful

        Raises:
            CalComError: If cancellation fails
        """
        log = self.logger.bind(operation="cancel_booking", booking_uid=booking_uid)

        try:
            client = await self.get_client()

            payload = {"reason": reason}

            await self._request_with_retry(
                "DELETE",
                f"{self.base_url}/bookings/{booking_uid}",
                json=payload,
                client=client,
            )

            log.info("booking_cancelled")
            return True

        except CalComError as e:
            log.error("cancel_booking_failed", error=str(e))
            raise
        except Exception as e:
            log.error("cancel_booking_unexpected_error", error=str(e))
            raise CalComError(f"Failed to cancel booking: {str(e)}") from e

    def generate_booking_url(
        self,
        event_type_id: int,
        contact_email: str,
        contact_name: str,
        contact_phone: str | None = None,
    ) -> str:
        """Generate a Cal.com booking URL with pre-filled attendee data.

        Args:
            event_type_id: Cal.com event type ID
            contact_email: Attendee email address
            contact_name: Attendee full name
            contact_phone: Optional phone number

        Returns:
            Cal.com booking URL with pre-filled data
        """
        log = self.logger.bind(
            operation="generate_booking_url",
            event_type_id=event_type_id,
            contact_email=contact_email,
        )

        try:
            # Cal.com public booking URL format
            base_url = f"https://cal.com/event/{event_type_id}"

            # Build query parameters for pre-filling
            params = [
                f"name={contact_name}",
                f"email={contact_email}",
            ]

            if contact_phone:
                # Clean phone number - remove common formatting
                phone_clean = "".join(c for c in contact_phone if c.isdigit() or c in "+-")
                params.append(f"phone={phone_clean}")

            url = f"{base_url}?{'&'.join(params)}"
            log.info("booking_url_generated")

            return url

        except Exception as e:
            log.error("generate_url_failed", error=str(e))
            raise CalComError(f"Failed to generate booking URL: {str(e)}") from e

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        client: httpx.AsyncClient,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make HTTP request with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: API endpoint URL
            client: HTTP client to use
            **kwargs: Additional arguments to pass to client request

        Returns:
            JSON response from API

        Raises:
            CalComError: If all retries fail
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
                        backoff_seconds = min(
                            backoff_seconds * 2, MAX_BACKOFF_SECONDS
                        )
                        continue

                    raise CalComRateLimitError("Rate limit exceeded, max retries reached")

                # Handle authentication errors
                if response.status_code == 401:
                    raise CalComAuthError("Invalid API key or authentication failed")

                # Handle not found
                if response.status_code == 404:
                    raise CalComNotFoundError("Resource not found on Cal.com")

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
                        # Retry on server errors
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds = min(
                            backoff_seconds * 2, MAX_BACKOFF_SECONDS
                        )
                        continue

                    raise CalComError(f"API error: {error_msg}")

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

                raise CalComError(f"Request timeout after {MAX_RETRIES} attempts") from e

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

                raise CalComError(f"Network error after {MAX_RETRIES} attempts") from e

        raise CalComError("Max retries exceeded")
