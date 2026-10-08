"""RF-019: local provider fixtures through real manual/follow-up boundaries."""

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_workspace
from app.api.service_errors import install_service_error_handler
from app.api.v1 import contacts, conversations
from app.db.session import get_db
from app.models.conversation import Message, MessageStatus
from app.services.contacts.contact_service import ContactService
from app.services.conversations.conversation_service import ConversationService
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.telephony.text_delivery import TextDeliveryError


class TextFixture:
    """No network, real DB, credentials, lifespan or production workers."""

    def __init__(self, outcome):
        self.workspace_id = UUID("00000000-0000-0000-0000-000000000019")
        self.conversation_id = UUID("00000000-0000-0000-0000-000000000020")
        self.next_at = datetime.now(UTC) + timedelta(hours=1)
        self.conversation = MagicMock(
            id=self.conversation_id,
            workspace_id=self.workspace_id,
            contact_id=19,
            contact_phone="+12025550101",
            workspace_phone="+12025550102",
            channel="sms",
            followup_count_sent=0,
            last_followup_at=None,
            next_followup_at=self.next_at,
            followup_enabled=True,
            followup_max_count=3,
            followup_delay_hours=24,
        )
        self.message = Message(
            id=uuid4(),
            conversation_id=self.conversation_id,
            direction="outbound",
            channel="sms",
            body="fixture draft",
            status=MessageStatus.QUEUED,
            is_ai=False,
            created_at=datetime.now(UTC),
            idempotency_key=uuid4(),
        )
        self.db = MagicMock(commit=AsyncMock(), refresh=AsyncMock(), flush=AsyncMock())

        def persist(message):
            message.id = uuid4()
            message.created_at = datetime.now(UTC)
            self.message = message

        self.db.add.side_effect = persist
        self.db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=self.message))
        )
        self.requests = []

        def handler(request):
            self.requests.append(request)
            if outcome == "rejected":
                return httpx.Response(
                    422, json={"errors": [{"code": "40300", "detail": "private provider detail"}]}
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "fixture-provider-id",
                        "to": [
                            {"status": "sending_failed" if outcome == "failed_2xx" else "queued"}
                        ],
                    }
                },
            )

        self.provider = TelnyxSMSService("local-fixture")
        self.provider.BASE_URL = "http://telnyx.fixture/v2"

        # Use the real HTTP parser, but never the production client factory.
        # A fresh mock-only client also makes repeated HTTP probes safe after close().
        async def post(payload, db, workspace_id, **kw):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url="http://telnyx.fixture/v2"
            ) as client:
                self.provider._client = client
                self.provider._provider_client = self.provider._build_provider_client(client)
                return await self.provider._post_message(payload, **kw)

        self.provider._post_workspace_message = AsyncMock(side_effect=post)
        self.stack = ExitStack()

    def start(self):
        for target in (
            "app.services.contacts.contact_service.get_text_message_provider",
            "app.services.conversations.conversation_service.get_text_message_provider",
            "app.workers.followup_worker.get_text_message_provider",
        ):
            self.stack.enter_context(patch(target, return_value=self.provider))
        self.stack.enter_context(
            patch.object(
                self.provider,
                "_get_or_create_conversation",
                AsyncMock(return_value=self.conversation),
            )
        )
        self.stack.enter_context(
            patch(
                "app.services.telephony.telnyx.shorten_urls_in_text",
                AsyncMock(side_effect=lambda body, **kw: body),
            )
        )
        self.stack.enter_context(
            patch("app.services.sla.record_first_response_and_maybe_alert", AsyncMock())
        )
        self.stack.enter_context(
            patch.object(
                ConversationService, "_get_conversation", AsyncMock(return_value=self.conversation)
            )
        )
        self.stack.enter_context(
            patch.object(
                ContactService,
                "get_contact",
                AsyncMock(return_value=MagicMock(phone_number="+12025550101")),
            )
        )
        self.stack.enter_context(
            patch.object(
                ContactService,
                "_get_workspace_phone",
                AsyncMock(
                    return_value=MagicMock(
                        id=uuid4(), phone_number="+12025550102", imessage_enabled=False
                    )
                ),
            )
        )
        self.app = FastAPI()
        install_service_error_handler(self.app)
        self.app.include_router(contacts.router, prefix="/contacts")
        self.app.include_router(conversations.router, prefix="/conversations")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: MagicMock(id=19)
        self.app.dependency_overrides[get_workspace] = lambda: MagicMock(id=self.workspace_id)
        return self

    async def close(self):
        self.stack.close()
        await self.provider.close()


@pytest.mark.parametrize("outcome", ["accepted", "rejected", "failed_2xx"])
@pytest.mark.parametrize("path", ["contact", "conversation", "followup"])
async def test_manual_text_http_acceptance(outcome, path):
    fixture = TextFixture(outcome).start()
    suffix = "followup/send" if path == "followup" else "messages"
    url = (
        "/contacts/19/messages"
        if path == "contact"
        else f"/conversations/{fixture.conversation_id}/{suffix}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fixture.app), base_url="http://fixture"
        ) as client:
            response = await client.post(
                url,
                params={"workspace_id": str(fixture.workspace_id)},
                json={"message" if path == "followup" else "body": "fixture draft"},
            )
        accepted = outcome == "accepted"
        assert response.status_code == (200 if accepted else 503), response.text
        assert fixture.message.status == (MessageStatus.SENT if accepted else MessageStatus.FAILED)
        fixture.db.commit.assert_awaited()
        assert len(fixture.requests) == 1
        assert fixture.requests[0].url.host == "telnyx.fixture"
        if outcome == "rejected":
            assert fixture.message.error_code == "40300"
        assert fixture.message.body == "fixture draft"
        assert fixture.conversation.followup_count_sent == (
            1 if accepted and path == "followup" else 0
        )
        if not accepted:
            assert "private provider detail" not in response.text
            assert fixture.conversation.next_followup_at == fixture.next_at
            assert fixture.conversation.last_followup_at is None
            assert fixture.message.sent_at is None
        if accepted and path == "followup":
            assert response.json()["success"] is True
    finally:
        await fixture.close()


async def test_repeated_manual_rejections_keep_history_and_use_only_mock_transport():
    fixture = TextFixture("rejected").start()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fixture.app), base_url="http://fixture"
        ) as client:
            ids = []
            for _ in range(2):
                response = await client.post(
                    "/contacts/19/messages",
                    params={"workspace_id": str(fixture.workspace_id)},
                    json={"body": "fixture draft"},
                )
                assert response.status_code == 503
                ids.append(response.json()["detail"]["details"]["message_id"])
            assert len(set(ids)) == 2
            assert len(fixture.requests) == 2
            assert all(request.url.host == "telnyx.fixture" for request in fixture.requests)
    finally:
        await fixture.close()


async def test_failed_idempotent_replay_never_becomes_success_or_resends():
    fixture = TextFixture("rejected").start()
    fixture.message.status = MessageStatus.FAILED
    try:
        with pytest.raises(TextDeliveryError) as error:
            await fixture.provider.send_message(
                to_number="+12025550101",
                from_number="+12025550102",
                body="fixture draft",
                db=fixture.db,
                workspace_id=fixture.workspace_id,
                idempotency_key=fixture.message.idempotency_key,
            )
        assert error.value.failed_message is fixture.message
        assert fixture.requests == []
        fixture.db.add.assert_not_called()
    finally:
        await fixture.close()
