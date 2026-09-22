"""Tests for operator vs prospect routing in the shared inbound text pipeline.

These lock in the widened operator channel: a registered operator texting in
(SMS or iMessage) is routed into the CRM assistant with the matching reply
channel, the Y/N approval fast-path still wins when it consumes the message,
and prospect messages still fall through to the contact AI pipeline.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.conversation import MessageChannel
from app.services.telephony import inbound_text
from app.services.telephony.inbound_text import InboundTextEvent, process_inbound_text_event


def _make_log() -> MagicMock:
    log = MagicMock()
    log.bind = MagicMock(return_value=log)
    return log


def _imessage_event() -> InboundTextEvent:
    return InboundTextEvent(
        provider_message_id="mac-relay:guid-1",
        from_number="+14155550100",  # operator's handset
        to_number="+12125550101",  # workspace sender identity
        body="how'd we do today?",
        workspace_id=uuid.uuid4(),
        channel=MessageChannel.IMESSAGE,
        response_channel="imessage",
    )


def _command_processor(*, consumes: bool) -> MagicMock:
    proc = MagicMock()
    proc.try_process_command = AsyncMock(return_value=consumes)
    return proc


@pytest.mark.asyncio
async def test_operator_imessage_routes_to_assistant_on_same_channel() -> None:
    """An operator iMessage hits the CRM assistant and replies over iMessage."""
    event = _imessage_event()
    db = MagicMock()
    operator = MagicMock()
    operator.id = 7
    check_operator = AsyncMock(return_value=operator)
    ingest = AsyncMock()
    process_assistant = AsyncMock(return_value=None)

    with patch(
        "app.services.ai.crm_assistant.process_assistant_message", process_assistant
    ):
        result = await process_inbound_text_event(
            db=db,
            event=event,
            ingest_message=ingest,
            log=_make_log(),
            command_processor=_command_processor(consumes=False),
            check_operator_fn=check_operator,
        )

    assert result is None
    ingest.assert_not_awaited()  # operator never enters the contact pipeline
    process_assistant.assert_awaited_once()
    kwargs = process_assistant.await_args.kwargs
    assert kwargs["user_id"] == 7
    assert kwargs["message"] == "how'd we do today?"
    assert kwargs["response_channel"] == "imessage"
    # Reply goes back to the operator's handset from the workspace identity.
    assert kwargs["sms_from_number"] == event.to_number
    assert kwargs["sms_to_number"] == event.from_number


@pytest.mark.asyncio
async def test_yes_no_fast_path_wins_over_assistant() -> None:
    """When the command processor consumes a Y/N, the assistant is not invoked."""
    event = _imessage_event()
    check_operator = AsyncMock()
    ingest = AsyncMock()
    process_assistant = AsyncMock()

    with patch(
        "app.services.ai.crm_assistant.process_assistant_message", process_assistant
    ):
        result = await process_inbound_text_event(
            db=MagicMock(),
            event=event,
            ingest_message=ingest,
            log=_make_log(),
            command_processor=_command_processor(consumes=True),
            check_operator_fn=check_operator,
        )

    assert result is None
    check_operator.assert_not_awaited()
    process_assistant.assert_not_awaited()
    ingest.assert_not_awaited()


@pytest.mark.asyncio
async def test_prospect_message_falls_through_to_contact_pipeline() -> None:
    """A non-operator sender ingests as a contact message and runs side effects."""
    event = _imessage_event()
    message = MagicMock()
    message.conversation_id = uuid.uuid4()
    ingest = AsyncMock(return_value=message)
    process_assistant = AsyncMock()
    side_effects = AsyncMock()

    with patch(
        "app.services.ai.crm_assistant.process_assistant_message", process_assistant
    ), patch.object(inbound_text, "run_inbound_text_side_effects", side_effects):
        result = await process_inbound_text_event(
            db=MagicMock(),
            event=event,
            ingest_message=ingest,
            log=_make_log(),
            command_processor=_command_processor(consumes=False),
            check_operator_fn=AsyncMock(return_value=None),
        )

    assert result is message
    process_assistant.assert_not_awaited()
    ingest.assert_awaited_once()
    side_effects.assert_awaited_once()
