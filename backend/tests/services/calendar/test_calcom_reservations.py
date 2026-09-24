"""Run real provider serialization/retry/cleanup against an HTTP transport fixture."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.services.ai.tool_executor import VoiceToolExecutor
from app.services.calendar.calcom import CalComError, CalComService
from app.services.providers.http import AsyncProviderHTTPClient


@pytest.fixture
def wire(monkeypatch):
    requests = []
    responses = []
    clients = []

    def handler(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    class WireClient(AsyncProviderHTTPClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs, transport=httpx.MockTransport(handler))
            clients.append(self)

    monkeypatch.setattr("app.services.calendar.calcom.AsyncProviderHTTPClient", WireClient)
    return requests, responses, clients


@pytest.mark.asyncio
async def test_reservation_and_release_wire_contract(wire):
    requests, responses, clients = wire
    hold = {
        "reservationUid": "hold-1",
        "reservationUntil": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    responses.extend(
        [
            httpx.Response(201, json={"status": "success", "data": hold}),
            httpx.Response(200, json={"status": "success"}),
        ]
    )
    service = CalComService("test")
    assert await service.reserve_slot(123, "2026-10-01T18:00:00Z") == hold
    assert clients[0].raw_client.is_closed
    await service.release_slot(hold["reservationUid"])
    await service.close()
    assert [r.method for r in requests] == ["POST", "DELETE"]
    assert requests[0].url.path == "/v2/slots/reservations"
    assert requests[1].url.path == "/v2/slots/reservations/hold-1"
    assert requests[0].headers["cal-api-version"] == "2024-09-04"
    assert requests[1].headers["cal-api-version"] == "2024-09-04"
    assert json.loads(requests[0].content) == {
        "eventTypeId": 123,
        "slotStart": "2026-10-01T18:00:00Z",
        "reservationDuration": 5,
    }


@pytest.mark.asyncio
async def test_expired_reservation_release_is_idempotent(wire):
    requests, responses, _clients = wire
    responses.append(httpx.Response(404, json={"message": "expired"}))
    service = CalComService("test")
    await service.release_slot("expired-hold")
    await service.close()
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"message": "unavailable"}),
        httpx.ReadTimeout("ambiguous"),
        httpx.Response(201, json={"status": "success", "data": {}}),
    ],
)
async def test_ambiguous_reservation_is_never_retried(wire, response):
    requests, responses, clients = wire
    responses.append(response)
    service = CalComService("test")
    with pytest.raises(CalComError):
        await service.reserve_slot(123, "2026-10-01T18:00:00Z")
    assert len(requests) == 1
    assert clients[0].raw_client.is_closed


@pytest.mark.asyncio
async def test_voice_booking_post_is_not_retried_after_timeout(wire):
    requests, responses, _clients = wire
    responses.append(httpx.ReadTimeout("ambiguous booking result"))
    executor = VoiceToolExecutor(agent=SimpleNamespace(calcom_event_type_id=123))
    service = executor._create_booking_service(123)
    try:
        with pytest.raises(CalComError):
            await service._calcom.create_booking(
                event_type_id=123,
                start_time_iso="2026-10-01T18:00:00Z",
                contact_name="Alice",
                contact_email="alice@example.test",
            )
    finally:
        await service.close()
    assert len(requests) == 1
    assert requests[0].method == "POST"


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["..", "../other", "a/b", "a?other=1", "", "a" * 257])
async def test_release_uid_cannot_change_request_path(wire, uid):
    requests, _responses, _clients = wire
    service = CalComService("test")
    with pytest.raises(CalComError, match="Invalid reservation UID"):
        await service.release_slot(uid)
    assert requests == []
