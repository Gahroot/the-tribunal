"""Text agent service for AI-powered SMS responses.

Handles:
- LLM calls for generating text responses
- Message context building
- Response generation with debouncing
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.conversation import Conversation, Message

logger = structlog.get_logger()

# Pending responses waiting for debounce
_pending_responses: dict[str, asyncio.Task[None]] = {}


def build_text_instructions(
    system_prompt: str,
    language: str = "en-US",
    timezone: str = "America/New_York",
    contact_phone: str | None = None,
) -> str:
    """Build instructions for text agent.

    Args:
        system_prompt: The agent's custom system prompt
        language: Language code (e.g., "en-US", "es-ES")
        timezone: Workspace timezone
        contact_phone: The contact's phone number

    Returns:
        Complete instructions string for text conversations
    """
    language_names = {
        "en-US": "English",
        "es-ES": "Spanish",
        "es-MX": "Mexican Spanish",
        "fr-FR": "French",
        "de-DE": "German",
        "pt-BR": "Brazilian Portuguese",
    }
    language_name = language_names.get(language, language)

    # Get current date/time
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        current_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")
    except Exception:
        current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    phone_context = f"\nContact Phone: {contact_phone}" if contact_phone else ""

    return f"""[CONTEXT]
Language: {language_name}
Timezone: {timezone}
Current: {current_datetime}
Channel: SMS/Text Message{phone_context}

[RESPONSE RULES]
- Respond ONLY in {language_name}
- All times are in {timezone} timezone
- Keep responses concise - SMS has character limits
- Be conversational but efficient
- Do not use markdown formatting (plain text only)

[YOUR ROLE]
{system_prompt}"""


async def build_message_context(
    conversation: Conversation,
    db: AsyncSession,
    max_messages: int = 20,
) -> list[dict[str, str]]:
    """Build message history for LLM context.

    Args:
        conversation: The conversation
        db: Database session
        max_messages: Maximum messages to include

    Returns:
        List of message dicts in OpenAI format
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
    )
    messages = list(reversed(result.scalars().all()))

    context: list[dict[str, str]] = []
    for msg in messages:
        role = "user" if msg.direction == "inbound" else "assistant"
        context.append({"role": role, "content": msg.body})

    return context


async def generate_text_response(
    agent: Agent,
    conversation: Conversation,
    db: AsyncSession,
    openai_api_key: str,
) -> str | None:
    """Generate AI response for a text conversation.

    Args:
        agent: The text agent to use
        conversation: The conversation
        db: Database session
        openai_api_key: OpenAI API key

    Returns:
        Generated response text, or None if failed
    """
    log = logger.bind(
        agent_id=str(agent.id),
        conversation_id=str(conversation.id),
    )
    log.info("generating_text_response")

    # Build message context
    messages = await build_message_context(
        conversation, db, max_messages=agent.text_max_context_messages
    )

    if not messages:
        log.warning("no_messages_in_context")
        return None

    # Build system instructions
    system_prompt = build_text_instructions(
        system_prompt=agent.system_prompt,
        language=agent.language,
        timezone="America/New_York",  # TODO: Get from workspace settings
        contact_phone=conversation.contact_phone,
    )

    # Create OpenAI client
    client = AsyncOpenAI(api_key=openai_api_key)

    try:
        # Build messages for API call
        api_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # Make LLM call
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=api_messages,
                temperature=agent.temperature,
                max_tokens=500,  # Limit for SMS
            ),
            timeout=30.0,
        )

        assistant_message = response.choices[0].message
        response_text = assistant_message.content

        if response_text:
            log.info("response_generated", length=len(response_text))
            return response_text

        return None

    except asyncio.TimeoutError:
        log.error("openai_timeout")
        return None
    except Exception:
        log.exception("openai_error")
        return None


async def process_inbound_with_ai(
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Process inbound message and generate AI response.

    Args:
        conversation_id: The conversation ID
        workspace_id: Workspace ID
        db: Database session
    """
    from app.services.telephony.telnyx import TelnyxSMSService

    log = logger.bind(conversation_id=str(conversation_id))
    log.info("processing_inbound_with_ai")

    # Get conversation with agent
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        log.error("conversation_not_found")
        return

    if not conversation.ai_enabled or conversation.ai_paused:
        log.info("ai_disabled_for_conversation")
        return

    if not conversation.assigned_agent_id:
        log.info("no_agent_assigned")
        return

    # Get agent
    agent_result = await db.execute(
        select(Agent).where(Agent.id == conversation.assigned_agent_id)
    )
    agent = agent_result.scalar_one_or_none()

    if not agent or not agent.is_active:
        log.info("agent_not_active")
        return

    # TODO: Get OpenAI API key from workspace settings
    openai_key = settings.openai_api_key
    if not openai_key:
        log.error("no_openai_api_key")
        return

    # Generate response
    response_text = await generate_text_response(
        agent=agent,
        conversation=conversation,
        db=db,
        openai_api_key=openai_key,
    )

    if not response_text:
        log.warning("no_response_generated")
        return

    # Send response via SMS
    telnyx_api_key = settings.telnyx_api_key
    if not telnyx_api_key:
        log.error("no_telnyx_api_key")
        return

    sms_service = TelnyxSMSService(telnyx_api_key)
    try:
        await sms_service.send_message(
            to_number=conversation.contact_phone,
            from_number=conversation.workspace_phone,
            body=response_text,
            db=db,
            workspace_id=workspace_id,
            agent_id=agent.id,
        )
        log.info("ai_response_sent")
    finally:
        await sms_service.close()


async def schedule_ai_response(
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    delay_ms: int = 3000,
) -> None:
    """Schedule an AI response after a delay (for message batching).

    If called multiple times for the same conversation within the delay,
    the timer resets to wait for more messages.

    Args:
        conversation_id: The conversation ID
        workspace_id: Workspace ID
        delay_ms: Delay in milliseconds before responding
    """
    from app.db.session import AsyncSessionLocal

    key = str(conversation_id)
    log = logger.bind(conversation_id=key, delay_ms=delay_ms)

    # Cancel any existing pending response
    if key in _pending_responses:
        _pending_responses[key].cancel()
        log.debug("cancelled_pending_response")

    async def delayed_response() -> None:
        """Execute response after delay."""
        log.info("delayed_response_started")
        try:
            await asyncio.sleep(delay_ms / 1000.0)

            # Process in new database session
            async with AsyncSessionLocal() as db:
                await process_inbound_with_ai(conversation_id, workspace_id, db)

        except asyncio.CancelledError:
            log.info("response_cancelled")
        except Exception:
            log.exception("delayed_response_error")
        finally:
            _pending_responses.pop(key, None)

    # Create and store task
    task = asyncio.create_task(delayed_response())
    _pending_responses[key] = task
    log.info("ai_response_scheduled")
