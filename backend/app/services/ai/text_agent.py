"""Text agent service for AI-powered SMS responses.

Handles:
- LLM calls for generating text responses
- Message context building
- Response generation with debouncing
- OpenAI function calling for booking appointments
- AI-powered opt-out intent classification

This module has been refactored to use extracted services:
- opt_out_detector: Opt-out keyword detection and AI classification
- text_tool_executor: Cal.com booking tool execution
- text_prompt_builder: System prompt construction
- voice_tools: Shared booking tool definitions
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.campaign import CampaignContact
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace

# Import from extracted modules
from app.services.ai.opt_out_detector import (
    classify_opt_out_intent,
    has_potential_opt_out_keywords,
)
from app.services.ai.text_prompt_builder import (
    FOLLOWUP_SYSTEM_PROMPT,
    build_booking_instructions,
    build_text_instructions,
)
from app.services.ai.text_tool_executor import TextToolExecutor
from app.services.ai.voice_tools import get_text_booking_tools

logger = structlog.get_logger()

# Default timezone fallback
DEFAULT_TIMEZONE = "America/New_York"

# Pending responses waiting for debounce
_pending_responses: dict[str, asyncio.Task[None]] = {}


async def get_workspace_timezone(
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Get timezone from workspace settings.

    Args:
        workspace_id: The workspace ID
        db: Database session

    Returns:
        Timezone string (e.g., "America/New_York")
    """
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace and workspace.settings:
        tz = workspace.settings.get("timezone")
        if isinstance(tz, str):
            return tz
    return DEFAULT_TIMEZONE


def _extract_email_from_messages(messages: list[dict[str, str]]) -> str | None:
    """Extract email address from conversation history.

    Searches through messages (newest first) for email addresses.

    Args:
        messages: List of message dicts with 'content' key

    Returns:
        The most recently mentioned email address, or None
    """
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    # Search from newest to oldest (reversed)
    for msg in reversed(messages):
        content = msg.get("content", "")
        match = re.search(email_pattern, content)
        if match:
            return match.group(0)

    return None


def _should_require_booking_tools(message: str) -> bool:  # noqa: PLR0911
    """Determine if booking tools should be required based on message content.

    Uses smarter matching to avoid false positives like "weather today".

    Args:
        message: The lowercased message to analyze

    Returns:
        True if booking tools should be required
    """
    # Direct booking intent phrases - always trigger
    direct_booking_phrases = [
        "book a", "book an", "schedule a", "schedule an",
        "set up a", "setup a", "arrange a",
        "want to meet", "want to call", "want to schedule",
        "like to meet", "like to call", "like to schedule",
        "can we meet", "can we call", "can we schedule",
        "let's meet", "lets meet", "let's schedule", "lets schedule",
        "interested in scheduling", "interested in meeting",
        "ready to book", "ready to schedule",
    ]
    if any(phrase in message for phrase in direct_booking_phrases):
        return True

    # Buying signals - general positive responses indicating readiness to proceed
    # These trigger booking tools so the AI offers to schedule instead of more questions
    buying_signal_phrases = [
        "sounds good", "that sounds great", "that sounds good",
        "ok sounds good", "okay sounds good",
        "i'm in", "im in", "count me in", "sign me up",
        "i'm interested", "im interested", "i'm ready", "im ready",
        "let's move forward", "lets move forward",
        "let's get started", "lets get started",
        "let's go", "lets go",
        "how do we get started", "how do i get started",
        "what's the next step", "whats the next step",
        "what do i need to do", "what do we do next",
        "i want that", "i need that", "i want this", "i need this",
        "yes please", "yeah that works", "yes that works",
    ]
    if any(phrase in message for phrase in buying_signal_phrases):
        return True

    # Availability questions - trigger tools
    availability_phrases = [
        "when are you", "when is he", "when is she", "when is nolan",
        "what times", "what time do", "what days",
        "any availability", "your availability", "his availability",
        "are you available", "is he available", "is she available",
        "when can we", "when can i", "when could we",
        "what's available", "whats available",
        "free time", "open slots", "available slots",
    ]
    if any(phrase in message for phrase in availability_phrases):
        return True

    # Time selection responses - user picking a slot
    # Must be in scheduling context (short message with time reference)
    time_selection_patterns = [
        r"\b(tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*\b(works|good|perfect|great|fine)\b",
        r"\b(works|good|perfect|great|fine)\b.*\b(tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"^(tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*(at\s*)?\d",
        r"^\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)?\s*(works|good|perfect|sounds|great)?",
        r"^(let's do|lets do|i'll take|ill take|how about)\s",
    ]
    for pattern in time_selection_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return True

    # Specific time mentions with booking context
    # Only trigger if message is SHORT and contains time (likely a time selection)
    if len(message) < 50:
        time_patterns = [
            r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b",  # "2pm", "2:30 pm"
            r"\bat\s+\d{1,2}\b",  # "at 2", "at 3"
            r"\b(morning|afternoon|evening)\s+(works|is good|sounds good)\b",
        ]
        for pattern in time_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

    # Email provided - likely confirming booking
    # Check for actual email pattern, not just "@" or ".com"
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    if re.search(email_pattern, message):
        return True

    # Email mention in booking context
    email_context_phrases = [
        "my email is", "email is", "send it to", "send confirmation to",
        "here's my email", "heres my email", "my email:",
    ]
    return any(phrase in message for phrase in email_context_phrases)


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


async def get_offer_context(
    conversation: Conversation,
    db: AsyncSession,
) -> str | None:
    """Get offer context for a conversation from its campaign.

    Args:
        conversation: The conversation
        db: Database session

    Returns:
        Formatted offer context string, or None if no offer
    """
    from sqlalchemy.orm import selectinload

    from app.models.campaign import Campaign

    # Get campaign contact for this conversation
    result = await db.execute(
        select(CampaignContact)
        .options(selectinload(CampaignContact.campaign).selectinload(Campaign.offer))
        .where(CampaignContact.conversation_id == conversation.id)
        .order_by(CampaignContact.created_at.desc())
        .limit(1)
    )
    campaign_contact = result.scalar_one_or_none()

    if not campaign_contact or not campaign_contact.campaign or not campaign_contact.campaign.offer:
        return None

    offer = campaign_contact.campaign.offer

    # Format discount text
    discount_text = ""
    if offer.discount_type == "percentage":
        discount_text = f"{offer.discount_value}% off"
    elif offer.discount_type == "fixed":
        discount_text = f"${offer.discount_value} off"
    elif offer.discount_type == "free_service":
        discount_text = "Free service"

    # Build context string
    context_parts = [f"The customer was offered: {offer.name}"]

    if discount_text:
        context_parts.append(f"Discount: {discount_text}")

    if offer.description:
        context_parts.append(f"Description: {offer.description}")

    if offer.terms:
        context_parts.append(f"Terms: {offer.terms}")

    context_parts.append("Refer to this offer in your responses if relevant to the conversation.")

    return "\n".join(context_parts)


async def get_booking_url(
    agent: Agent,
    conversation: Conversation,
    db: AsyncSession,
) -> str | None:
    """Get Cal.com booking URL for an agent with pre-filled contact information.

    Args:
        agent: The agent with potential calcom_event_type_id
        conversation: The conversation
        db: Database session

    Returns:
        Cal.com booking URL with pre-filled parameters, or None if not configured
    """
    from app.utils.calendar import generate_booking_url

    # Check if agent has a Cal.com event type configured
    if not agent.calcom_event_type_id:
        return None

    # Try to get contact info if available
    contact_email: str | None = None
    contact_name: str | None = None

    # Load contact if conversation has one
    if conversation.contact_id:
        result = await db.execute(
            select(Contact).where(Contact.id == conversation.contact_id)
        )
        contact = result.scalar_one_or_none()
        if contact:
            contact_email = contact.email
            contact_name = contact.full_name

    # Build the booking URL with contact pre-fill
    booking_url = generate_booking_url(
        event_type_id=agent.calcom_event_type_id,
        contact_email=contact_email,
        contact_name=contact_name,
        contact_phone=conversation.contact_phone,
    )

    return booking_url


async def generate_text_response(  # noqa: PLR0915, PLR0912
    agent: Agent,
    conversation: Conversation,
    db: AsyncSession,
    openai_api_key: str,
) -> str | None:
    """Generate AI response for a text conversation.

    Supports OpenAI function calling for booking appointments via Cal.com.

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

    # Get timezone from workspace settings
    timezone = await get_workspace_timezone(conversation.workspace_id, db)

    # Build message context
    messages = await build_message_context(
        conversation, db, max_messages=agent.text_max_context_messages
    )

    if not messages:
        log.warning("no_messages_in_context")
        return None

    # Get offer context if conversation was from a campaign
    offer_context = await get_offer_context(conversation, db)

    # Build system instructions - include booking tools info if configured
    has_booking_tools = bool(
        agent.calcom_event_type_id
        and settings.calcom_api_key
        and "book_appointment" in (agent.enabled_tools or [])
    )

    booking_instructions = ""
    extracted_email = None
    if has_booking_tools:
        # Extract email from conversation history
        extracted_email = _extract_email_from_messages(messages)

        # Build booking instructions using extracted module
        booking_instructions = build_booking_instructions(
            timezone=timezone,
            extracted_email=extracted_email,
        )

        # Log extracted email for debugging
        if extracted_email:
            log.info("email_extracted_from_history", email=extracted_email)

    system_prompt = build_text_instructions(
        system_prompt=agent.system_prompt + booking_instructions,
        language=agent.language,
        timezone=timezone,
        contact_phone=conversation.contact_phone,
        offer_context=offer_context,
        booking_url=None,  # Don't include URL when using function calling
    )

    # Create OpenAI client
    client = AsyncOpenAI(api_key=openai_api_key)

    try:
        # Build messages for API call
        api_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # Prepare API call parameters
        api_params: dict[str, Any] = {
            "model": "gpt-4o-mini",
            "messages": api_messages,
            "temperature": agent.temperature,
            "max_tokens": 500,
        }

        # Include tools if booking is configured
        if has_booking_tools:
            api_params["tools"] = get_text_booking_tools(timezone)
            # Check if last message mentions booking-related keywords
            last_msg = messages[-1]["content"].lower() if messages else ""

            # OPT-OUT DETECTION: Never force booking tools on negative intent
            # These phrases indicate user wants to stop communication
            opt_out_phrases = [
                "stop", "unsubscribe", "opt out", "optout", "cancel",
                "remove me", "take me off", "don't text", "dont text",
                "don't contact", "dont contact", "leave me alone",
                "not interested", "no thanks", "no thank you",
                "spam", "harassment", "harassing", "reported",
                "wrong number", "wrong person",
            ]
            is_opt_out = any(phrase in last_msg for phrase in opt_out_phrases)

            if is_opt_out:
                # Don't force tools on opt-out messages - let AI respond naturally
                api_params["tool_choice"] = "auto"
                log.info("opt_out_detected_tools_auto")
            else:
                # Check for booking intent using smarter matching
                should_require_tools = _should_require_booking_tools(last_msg)

                if should_require_tools:
                    api_params["tool_choice"] = "required"
                    log.info("booking_tools_required")
                else:
                    api_params["tool_choice"] = "auto"
                    log.info("booking_tools_enabled")

        # Make initial LLM call
        response = await asyncio.wait_for(
            client.chat.completions.create(**api_params),
            timeout=30.0,
        )

        assistant_message = response.choices[0].message

        # Handle tool calls if present
        if assistant_message.tool_calls:
            log.info(
                "tool_calls_received",
                count=len(assistant_message.tool_calls),
            )

            # Execute the tool calls using TextToolExecutor
            tool_executor = TextToolExecutor(
                agent=agent,
                conversation=conversation,
                db=db,
                timezone=timezone,
            )
            tool_results = await tool_executor.handle_tool_calls(
                tool_calls=assistant_message.tool_calls,
            )

            # Add assistant message and tool results to conversation
            api_messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ],
            })
            api_messages.extend(tool_results)

            # Make follow-up call to get final response
            follow_up_response = await asyncio.wait_for(
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=api_messages,  # type: ignore[arg-type]
                    temperature=agent.temperature,
                    max_tokens=500,
                ),
                timeout=30.0,
            )

            final_message = follow_up_response.choices[0].message
            final_text: str | None = final_message.content

            if final_text:
                log.info(
                    "response_generated_with_tools",
                    length=len(final_text),
                )
                return final_text
        else:
            # No tool calls, use direct response
            response_text: str | None = assistant_message.content
            if response_text:
                log.info("response_generated", length=len(response_text))
                return response_text

        return None

    except TimeoutError:
        log.error("openai_timeout")
        return None
    except Exception:
        log.exception("openai_error")
        return None


async def process_inbound_with_ai(  # noqa: PLR0911
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Process inbound message and generate AI response.

    Includes AI-powered opt-out detection that runs during the debounce delay,
    distinguishing between genuine opt-outs and false positives like
    "I think you should quit" (insult) vs "quit texting me" (opt-out).

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

    # === AI-POWERED OPT-OUT DETECTION ===
    # Get last inbound message to check for opt-out intent
    last_msg_result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_inbound = last_msg_result.scalar_one_or_none()

    if last_inbound and has_potential_opt_out_keywords(last_inbound.body):
        log.info("potential_opt_out_detected", message_preview=last_inbound.body[:50])

        # Get conversation context for better classification
        messages_context = await build_message_context(conversation, db, max_messages=5)

        # Run AI classifier to verify intent
        is_genuine_opt_out = await classify_opt_out_intent(
            message=last_inbound.body,
            conversation_context=messages_context,
            openai_api_key=openai_key,
        )

        if is_genuine_opt_out:
            # Confirmed opt-out - disable AI and don't respond
            conversation.ai_enabled = False
            await db.commit()
            log.info(
                "opt_out_confirmed_by_ai",
                message=last_inbound.body[:100],
            )
            return
        else:
            log.info(
                "opt_out_rejected_by_ai",
                message=last_inbound.body[:100],
            )
            # Not a genuine opt-out - proceed with normal response

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
        log.info(
            "ai_response_sent",
            response_length=len(response_text),
        )
    except Exception as e:
        log.error(
            "failed_to_send_ai_response",
            error=str(e),
            error_type=type(e).__name__,
        )
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


async def generate_followup_message(
    conversation: Conversation,
    db: AsyncSession,
    openai_api_key: str,
    custom_instructions: str | None = None,
) -> str | None:
    """Generate an AI follow-up message for a conversation.

    Creates a contextual re-engagement message based on conversation history,
    time since last interaction, and optional custom instructions.

    Args:
        conversation: The conversation to generate a follow-up for
        db: Database session
        openai_api_key: OpenAI API key
        custom_instructions: Optional custom instructions to guide the message

    Returns:
        Generated follow-up message text, or None if generation failed
    """
    log = logger.bind(conversation_id=str(conversation.id))
    log.info("generating_followup_message")

    # Build message context
    messages = await build_message_context(conversation, db, max_messages=10)

    if not messages:
        log.warning("no_messages_in_context_for_followup")
        return None

    # Get contact name for personalization
    contact_name = "there"
    if conversation.contact_id:
        result = await db.execute(
            select(Contact).where(Contact.id == conversation.contact_id)
        )
        contact = result.scalar_one_or_none()
        if contact and contact.first_name:
            contact_name = contact.first_name

    # Calculate time since last message
    time_context = ""
    if conversation.last_message_at:
        time_diff = datetime.now(UTC) - conversation.last_message_at.replace(tzinfo=UTC)
        days = time_diff.days
        hours = time_diff.seconds // 3600

        if days > 0:
            time_context = f"\nTime since last message: {days} day{'s' if days != 1 else ''}"
        elif hours > 0:
            time_context = f"\nTime since last message: {hours} hour{'s' if hours != 1 else ''}"

    # Build the system prompt with context
    system_prompt = FOLLOWUP_SYSTEM_PROMPT
    if custom_instructions:
        system_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{custom_instructions}"

    # Build user prompt with context
    user_prompt = f"""Generate a follow-up message for this conversation.

Contact name: {contact_name}
Previous follow-ups sent: {conversation.followup_count_sent}{time_context}

Recent conversation:
"""
    for msg in messages[-6:]:  # Last 6 messages for context
        role = "Customer" if msg["role"] == "user" else "You"
        user_prompt += f"\n{role}: {msg['content']}"

    user_prompt += "\n\nWrite a short, friendly follow-up message:"

    # Create OpenAI client
    client = AsyncOpenAI(api_key=openai_api_key)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=200,
            ),
            timeout=30.0,
        )

        followup_text: str | None = response.choices[0].message.content
        if followup_text:
            followup_text = followup_text.strip()
            log.info("followup_message_generated", length=len(followup_text))
            return followup_text

        return None

    except TimeoutError:
        log.error("followup_generation_timeout")
        return None
    except Exception:
        log.exception("followup_generation_error")
        return None
