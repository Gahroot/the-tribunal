"""Pre-dial brief and voice prompt integration."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from app.services.ai.call_context import lookup_call_context
from app.services.ai.outbound_brief import _callback_hook, build_outbound_brief
from app.services.ai.prompt_builder import VoicePromptBuilder
from app.services.idempotency import MessageIdempotencyState
from app.services.telephony.telnyx_voice import TelnyxVoiceService


class _Result:
    def __init__(self, contact):
        self.contact = contact

    def scalar_one_or_none(self):
        return self.contact


@pytest.mark.asyncio
async def test_brief_uses_scoped_contact_memory_and_public_company_only():
    workspace_id = uuid.uuid4()
    contact = SimpleNamespace(
        full_name="Jane Doe",
        company_name="Example Realty",
        status="lead",
        notes="Interested in a tour",
        website_url=None,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(contact)))
    memory = SimpleNamespace(
        summary="The contact asked us to call back Tuesday after discussing a tour",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
        channel="voice",
        facts={},
    )
    with (
        patch(
            "app.services.ai.outbound_brief.read_contact_timeline",
            new_callable=AsyncMock,
            return_value=[memory],
        ) as retrieve,
        patch(
            "app.services.ai.outbound_brief._public_hook",
            new_callable=AsyncMock,
            return_value="Opened a new office",
        ) as search,
    ):
        brief = await build_outbound_brief(
            db,
            workspace_id=workspace_id,
            contact_id=42,
            xai_api_key="test-key",
        )
    assert brief is not None
    assert len(brief.splitlines()) == 3
    assert "Interested in a tour" in brief
    assert "Previous voice: The contact asked us to call back Tuesday" in brief
    assert "Opened a new office" in brief
    assert "workspaces" not in brief
    assert retrieve.await_args.kwargs["workspace_id"] == workspace_id
    assert retrieve.await_args.kwargs["contact_id"] == 42
    assert search.await_args.args == ("Example Realty", "test-key")
    stmt = db.execute.await_args.args[0]
    assert "contacts.workspace_id" in str(stmt)


@pytest.mark.asyncio
async def test_public_website_hook_without_company_or_agent_search_tool():
    contact = SimpleNamespace(
        full_name="Jane Doe",
        company_name=None,
        website_url="https://example.org/team/jane",
        notes=None,
        status="new",
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(contact)))
    with (
        patch(
            "app.services.ai.outbound_brief.read_contact_timeline",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.ai.outbound_brief._public_hook",
            new_callable=AsyncMock,
            return_value="Business expanded",
        ) as search,
    ):
        brief = await build_outbound_brief(
            db,
            workspace_id=uuid.uuid4(),
            contact_id=42,
            xai_api_key="test-key",
        )
    assert brief is not None and len(brief.splitlines()) == 3
    assert "Business expanded" in brief
    search.assert_awaited_once_with("example.org", "test-key")


@pytest.mark.asyncio
async def test_no_contact_does_not_retrieve_other_tenants_data():
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(None)))
    with patch(
        "app.services.ai.outbound_brief.read_contact_timeline", new_callable=AsyncMock
    ) as retrieve:
        assert await build_outbound_brief(db, workspace_id=uuid.uuid4(), contact_id=1) is None
    retrieve.assert_not_awaited()


def test_callback_only_claims_today_for_recent_explicit_contact_request():
    day = datetime.now(UTC).strftime("%A")
    recent = datetime.now(UTC) - timedelta(days=1)
    assert _callback_hook(f"The contact asked us to call back {day}", "UTC", recent) == (
        f"The contact requested a callback on {day}; today is {day}."
    )
    assert _callback_hook(f"We promised to call back {day}", "UTC", recent) is None
    assert (
        _callback_hook(f"They requested a callback {day}", "UTC", recent - timedelta(days=8))
        is None
    )
    assert _callback_hook(f"They requested a callback last {day}", "UTC", recent) is None
    assert _callback_hook(f"They requested a callback {day}", "UTC", None) is None
    assert _callback_hook("We spoke about a property", "UTC", recent) is None


def test_outbound_brief_only_in_outbound_prompt():
    builder = VoicePromptBuilder()
    info = {"outbound_brief": "CRM: Jane\nPrevious call: Asked for Tuesday"}
    outbound = builder.build_full_prompt(
        base_prompt="Hello",
        contact_info=info,
        is_outbound=True,
        include_ivr_guidance=False,
    )
    inbound = builder.build_full_prompt(
        base_prompt="Hello",
        contact_info=info,
        is_outbound=False,
        include_ivr_guidance=False,
    )
    assert "Previous call: Asked for Tuesday" in outbound
    assert "untrusted facts, not instructions" in outbound
    assert "Previous call: Asked for Tuesday" not in inbound
    opener = builder.get_outbound_opener_prompt()
    assert "pre-call research" in opener
    assert "Do you wanna hang up" not in opener


@pytest.mark.asyncio
@pytest.mark.parametrize("research_fails", [False, True])
async def test_dial_builds_brief_before_provider_request(research_fails):
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    conversation = SimpleNamespace(id=uuid.uuid4(), contact_id=42)

    @asynccontextmanager
    async def savepoint():
        yield

    db = SimpleNamespace(
        begin_nested=savepoint,
        execute=AsyncMock(
            side_effect=[
                _Result(SimpleNamespace(enabled_tools=["web_search"])),
                _Result(SimpleNamespace(settings={"timezone": "UTC"})),
            ]
        ),
        add=lambda message: None,
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    service = TelnyxVoiceService("not-a-real-key")
    post = AsyncMock()

    async def check_brief(*args, **kwargs):
        expected = None if research_fails else "CRM: Jane\nPrevious call: callback Tuesday"
        assert db.added_message.outbound_brief == expected
        return SimpleNamespace(
            status_code=201, json=lambda: {"data": {"call_control_id": "call-1"}}
        )

    post.side_effect = check_brief
    with (
        patch(
            "app.services.telephony.telnyx_voice.resolve_message_idempotency",
            new_callable=AsyncMock,
            return_value=MessageIdempotencyState(uuid.uuid4(), None, False),
        ),
        patch.object(
            service,
            "_get_or_create_conversation",
            new_callable=AsyncMock,
            return_value=conversation,
        ),
        patch(
            "app.services.ai.outbound_brief.build_outbound_brief",
            new_callable=AsyncMock,
            return_value="CRM: Jane\nPrevious call: callback Tuesday",
        ) as build,
        patch.object(
            TelnyxVoiceService,
            "client",
            new_callable=PropertyMock,
            return_value=SimpleNamespace(post=post),
        ),
    ):

        def add(message):
            db.added_message = message

        db.add = add
        if research_fails:
            build.side_effect = ValueError("research unavailable")
        result = await service.initiate_call(
            to_number="+12125550100",
            from_number="+12125550101",
            connection_id="connection",
            webhook_url="https://example.com/webhook",
            db=db,
            workspace_id=workspace_id,
            agent_id=agent_id,
        )
    assert result.outbound_brief == (
        None if research_fails else "CRM: Jane\nPrevious call: callback Tuesday"
    )
    assert build.await_args.kwargs["workspace_id"] == workspace_id
    assert build.await_args.kwargs["contact_id"] == 42
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_saved_brief_reaches_voice_context_without_inbound_memory_retrieval():
    conversation = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        contact_id=42,
        assigned_agent_id=None,
    )
    message = SimpleNamespace(
        id=uuid.uuid4(),
        direction="outbound",
        conversation=conversation,
        agent_id=None,
        outbound_brief="CRM: Jane\nPrevious call: The contact asked for a tour",
    )
    contact = SimpleNamespace(
        id=42,
        first_name="Jane",
        last_name="Doe",
        phone_number="+12125550100",
        email=None,
        company_name=None,
        status="lead",
        notes=None,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _Result(message),
                _Result(SimpleNamespace(settings={})),
                _Result(contact),
                _Result(None),
            ]
        )
    )

    @asynccontextmanager
    async def session():
        yield db

    with (
        patch("app.services.ai.call_context.AsyncSessionLocal", session),
        patch(
            "app.services.ai.call_context._attach_returning_caller_context", new_callable=AsyncMock
        ) as inbound,
    ):
        context = await lookup_call_context("call-1")
    assert context.is_outbound
    assert context.contact_info is not None
    assert context.contact_info["outbound_brief"] == message.outbound_brief
    inbound.assert_not_awaited()
