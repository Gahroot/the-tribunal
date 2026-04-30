"""CRM assistant processor — orchestrates LLM + tool execution for operator chat."""

import asyncio
import json
import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assistant_conversation import AssistantConversation, AssistantMessage
from app.services.ai.crm_assistant._tool_executor import CRMToolExecutor
from app.services.ai.crm_assistant._tools import get_crm_tools

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
You are a CRM management assistant. You help the user manage their CRM by searching \
contacts, creating records, sending messages, checking campaigns, and more. \
Be concise and helpful. When performing actions, confirm what you did. \
Available tools let you search contacts, create contacts, list campaigns, \
manage agents, send SMS, read conversations, check appointments, \
and view dashboard stats.\
"""


async def process_assistant_message(  # noqa: PLR0912, PLR0913, PLR0915
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: int,
    message: str,
    response_channel: str = "in_app",
    sms_from_number: str | None = None,
    sms_to_number: str | None = None,
) -> str:
    """Process an operator message through the CRM assistant.

    Args:
        db: Database session.
        workspace_id: Workspace scope.
        user_id: Operator's user ID.
        message: The operator's text message.
        response_channel: "in_app" or "sms".
        sms_from_number: Telnyx number to send from (for SMS responses).
        sms_to_number: Operator's phone number (for SMS responses).

    Returns:
        The assistant's response text.
    """
    log = logger.bind(
        workspace_id=str(workspace_id),
        user_id=user_id,
        channel=response_channel,
    )
    log.info("processing_assistant_message")

    # ── 1. Get or create conversation ──────────────────────────────────
    conv_result = await db.execute(
        select(AssistantConversation).where(
            AssistantConversation.workspace_id == workspace_id,
            AssistantConversation.user_id == user_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()

    if conversation is None:
        conversation = AssistantConversation(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        db.add(conversation)
        await db.flush()

    # ── 2. Append user message ─────────────────────────────────────────
    user_msg = AssistantMessage(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    # ── 3. Load recent history ─────────────────────────────────────────
    history_result = await db.execute(
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == conversation.id)
        .order_by(AssistantMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(history_result.scalars().all()))

    api_messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        api_messages.append(entry)

    # ── 4. Call LLM with tools ─────────────────────────────────────────
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    actions_taken: list[dict[str, Any]] = []

    try:
        api_params: dict[str, Any] = {
            "model": "gpt-5.4-nano",
            "messages": api_messages,
            "tools": get_crm_tools(),
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_completion_tokens": 800,
        }
        response = await asyncio.wait_for(
            client.chat.completions.create(**api_params),
            timeout=45.0,
        )

        assistant_message = response.choices[0].message

        # ── 5. Handle tool calls ───────────────────────────────────────
        if assistant_message.tool_calls:
            # Save assistant message with tool calls
            tool_calls_data = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ]
            assistant_msg = AssistantMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message.content or "",
                tool_calls=tool_calls_data,
            )
            db.add(assistant_msg)
            await db.flush()

            # Add assistant + tool results to API messages
            api_messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": tool_calls_data,
            })

            executor = CRMToolExecutor(db=db, workspace_id=workspace_id, user_id=user_id)
            for tc in assistant_message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result = await executor.execute(tc.function.name, arguments)
                actions_taken.append({
                    "tool_name": tc.function.name,
                    "success": result.get("success", False),
                    "summary": json.dumps(result)[:200],
                })

                tool_result_msg = AssistantMessage(
                    conversation_id=conversation.id,
                    role="tool",
                    content=json.dumps(result),
                    tool_call_id=tc.id,
                )
                db.add(tool_result_msg)

                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

            await db.flush()

            # ── 6. Follow-up LLM call for natural language ─────────────
            follow_up_params: dict[str, Any] = {
                "model": "gpt-5.4-nano",
                "messages": api_messages,
                "temperature": 0.3,
                "max_completion_tokens": 500,
            }
            follow_up = await asyncio.wait_for(
                client.chat.completions.create(**follow_up_params),
                timeout=30.0,
            )
            final_text: str | None = follow_up.choices[0].message.content

            if final_text:
                final_msg = AssistantMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=final_text,
                )
                db.add(final_msg)
                await db.flush()
                await db.commit()

                # Send via SMS if needed
                if response_channel == "sms" and sms_from_number and sms_to_number:
                    await _send_sms_response(
                        sms_from_number, sms_to_number, final_text, db, workspace_id, log,
                    )

                return final_text

            await db.commit()
            return "I processed your request but couldn't generate a response."

        # No tool calls — direct response
        response_text: str | None = assistant_message.content
        if response_text:
            final_msg = AssistantMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=response_text,
            )
            db.add(final_msg)
            await db.flush()
            await db.commit()

            if response_channel == "sms" and sms_from_number and sms_to_number:
                await _send_sms_response(
                    sms_from_number, sms_to_number, response_text, db, workspace_id, log,
                )

            return response_text

        await db.commit()
        return "I couldn't generate a response."

    except TimeoutError:
        log.error("assistant_llm_timeout")
        await db.commit()
        return "Sorry, that took too long. Please try again."
    except Exception:
        log.exception("assistant_processing_error")
        await db.commit()
        return "Something went wrong processing your request. Please try again."


async def _send_sms_response(
    from_number: str,
    to_number: str,
    body: str,
    db: AsyncSession,
    workspace_id: uuid.UUID,
    log: Any,
) -> None:
    """Send the assistant response via SMS."""
    from app.services.telephony.telnyx import TelnyxSMSService

    telnyx_key = settings.telnyx_api_key
    if not telnyx_key:
        log.warning("no_telnyx_key_for_sms_response")
        return

    sms_service = TelnyxSMSService(telnyx_key)
    try:
        await sms_service.send_message(
            to_number=to_number,
            from_number=from_number,
            body=body,
            db=db,
            workspace_id=workspace_id,
        )
        log.info("assistant_sms_sent", to=to_number)
    except Exception:
        log.exception("assistant_sms_send_failed")
    finally:
        await sms_service.close()
