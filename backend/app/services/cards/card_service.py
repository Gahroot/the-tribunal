"""Physical card sending via Lob API."""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class CardService:
    """Send physical postcards via Lob API."""

    LOB_API_URL = "https://api.lob.com/v1/postcards"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def send_postcard(
        self,
        to_name: str,
        to_address_line1: str,
        to_address_city: str,
        to_address_state: str,
        to_address_zip: str,
        from_name: str,
        from_address_line1: str,
        from_address_city: str,
        from_address_state: str,
        from_address_zip: str,
        front_html: str,
        back_html: str,
        to_address_line2: str = "",
        from_address_line2: str = "",
    ) -> dict[str, Any]:
        """Send a postcard via Lob API.

        Lob uses HTTP Basic Auth with the API key as username and empty password.
        Form data is sent (not JSON) with nested address fields using bracket notation.
        Returns the Lob API response dict.
        Raises httpx.HTTPStatusError on API errors.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.LOB_API_URL,
                auth=(self.api_key, ""),
                data={
                    "to[name]": to_name,
                    "to[address_line1]": to_address_line1,
                    "to[address_line2]": to_address_line2,
                    "to[address_city]": to_address_city,
                    "to[address_state]": to_address_state,
                    "to[address_zip]": to_address_zip,
                    "from[name]": from_name,
                    "from[address_line1]": from_address_line1,
                    "from[address_line2]": from_address_line2,
                    "from[address_city]": from_address_city,
                    "from[address_state]": from_address_state,
                    "from[address_zip]": from_address_zip,
                    "front": front_html,
                    "back": back_html,
                    "size": "4x6",
                },
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            logger.info("postcard_sent", lob_id=result.get("id"))
            return result
