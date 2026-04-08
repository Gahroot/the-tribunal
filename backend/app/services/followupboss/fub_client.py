"""Follow Up Boss API client."""

import httpx
import structlog

logger = structlog.get_logger()

BASE_URL = "https://api.followupboss.com/v1"


class FollowUpBossClient:
    """Async client for the Follow Up Boss REST API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            auth=(api_key, ""),
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )

    async def verify(self) -> dict:  # type: ignore[type-arg]
        """Test API key by calling /me endpoint."""
        resp = await self._client.get("/me")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def get_people(
        self,
        limit: int = 100,
        offset: int = 0,
        sort: str = "-created",
    ) -> dict:  # type: ignore[type-arg]
        """Fetch contacts/leads."""
        resp = await self._client.get(
            "/people",
            params={"limit": limit, "offset": offset, "sort": sort},
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def get_person(self, person_id: int) -> dict:  # type: ignore[type-arg]
        """Fetch a single contact by ID."""
        resp = await self._client.get(f"/people/{person_id}")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def create_note(
        self,
        person_id: int,
        subject: str,
        body: str,
    ) -> dict:  # type: ignore[type-arg]
        """Push a note back to a FUB contact."""
        resp = await self._client.post(
            "/notes",
            json={
                "personId": person_id,
                "subject": subject,
                "body": body,
                "isHtml": False,
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def create_event(
        self,
        source: str,
        event_type: str,
        message: str,
        person: dict,  # type: ignore[type-arg]
    ) -> dict:  # type: ignore[type-arg]
        """Create an event (preferred way to push lead data)."""
        resp = await self._client.post(
            "/events",
            json={
                "source": source,
                "system": "TheTribunal",
                "type": event_type,
                "message": message,
                "person": person,
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
