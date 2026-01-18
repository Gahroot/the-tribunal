"""Text agent service for AI-powered SMS responses.

Handles:
- LLM calls for generating text responses
- Message context building
- Response generation with debouncing
- OpenAI function calling for booking appointments
- AI-powered opt-out intent classification
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.campaign import CampaignContact
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace
from app.services.calendar.calcom import CalComService

# Default timezone fallback
DEFAULT_TIMEZONE = "America/New_York"

# Opt-out keywords that trigger AI classification
# These are potential opt-out signals that need context verification
OPT_OUT_KEYWORDS = [
    "stop", "stopall", "unsubscribe", "opt out", "optout",
    "cancel", "end", "quit", "remove", "unsub",
    # Additional phrases for edge cases
    "take me off", "don't want", "dont want", "no more messages",
    "stop messaging", "stop texting", "leave me alone",
]

# System prompt for opt-out classification
OPT_OUT_CLASSIFIER_PROMPT = """You are a message intent classifier. Determine if the user \
is requesting to opt out of receiving messages (SMS/text communications).

TRUE OPT-OUT examples (user wants to stop receiving messages):
- "STOP"
- "Stop texting me"
- "Unsubscribe"
- "Remove me from this list"
- "I don't want these messages anymore"
- "Quit sending me texts"
- "Please stop contacting me"

FALSE OPT-OUT examples (NOT requesting to stop messages):
- "I think you should quit" (telling someone to quit their job/give up)
- "Don't quit on me" (encouragement)
- "I quit my job last week" (unrelated statement)
- "Stop wasting my time with bad offers" (complaint, but still engaged)
- "This is the end of our conversation" (ending chat, not unsubscribing)
- "Cancel my appointment" (canceling something else, not messages)
- "Remove my name from the appointment" (editing, not unsubscribing)

Respond with ONLY "true" or "false" - no other text."""


def has_potential_opt_out_keywords(message: str) -> bool:
    """Check if message contains potential opt-out keywords.

    This is a fast pre-filter before running the AI classifier.

    Args:
        message: The message text to check

    Returns:
        True if message contains any opt-out keywords
    """
    message_normalized = re.sub(r"[^\w\s]", "", message.lower().strip())
    return any(keyword in message_normalized for keyword in OPT_OUT_KEYWORDS)


async def classify_opt_out_intent(
    message: str,
    conversation_context: list[dict[str, str]] | None = None,
    openai_api_key: str | None = None,
) -> bool:
    """Use AI to determine if a message is a genuine opt-out request.

    This function uses GPT-4o-mini to understand the semantic intent
    of a message, distinguishing between actual opt-out requests and
    messages that happen to contain opt-out keywords in other contexts.

    Args:
        message: The message to classify
        conversation_context: Optional recent conversation history for context
        openai_api_key: OpenAI API key (uses settings if not provided)

    Returns:
        True if the message is a genuine opt-out request, False otherwise
    """
    log = logger.bind(message_preview=message[:50] if message else "")

    api_key = openai_api_key or settings.openai_api_key
    if not api_key:
        log.warning("no_openai_key_for_opt_out_classifier")
        # Fall back to keyword-only detection if no API key
        return has_potential_opt_out_keywords(message)

    # Build the user message with context if available
    context_text = ""
    if conversation_context and len(conversation_context) > 0:
        # Include last 3 messages for context
        recent = conversation_context[-3:]
        context_lines = []
        for msg in recent:
            role = "Customer" if msg["role"] == "user" else "Agent"
            context_lines.append(f"{role}: {msg['content']}")
        context_text = "Recent conversation:\n" + "\n".join(context_lines) + "\n\n"

    user_message = f"""{context_text}Message to classify: "{message}"

Is this a genuine opt-out request (user wants to stop receiving SMS/text messages)?"""

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": OPT_OUT_CLASSIFIER_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,  # Deterministic for classification
                max_tokens=10,  # Only need "true" or "false"
            ),
            timeout=5.0,  # Fast timeout for classification
        )

        result_text = response.choices[0].message.content or ""
        is_opt_out = result_text.strip().lower() == "true"

        log.info(
            "opt_out_classified",
            result=is_opt_out,
            raw_response=result_text.strip(),
        )

        return is_opt_out

    except TimeoutError:
        log.warning("opt_out_classifier_timeout")
        # On timeout, be conservative and check keywords only
        # If message is just "STOP" or "unsubscribe", treat as opt-out
        simple_opt_outs = ["stop", "stopall", "unsubscribe", "opt out", "optout"]
        return message.lower().strip() in simple_opt_outs

    except Exception as e:
        log.exception("opt_out_classifier_error", error=str(e))
        # On error, fall back to simple keyword check for obvious opt-outs
        simple_opt_outs = ["stop", "stopall", "unsubscribe", "opt out", "optout"]
        return message.lower().strip() in simple_opt_outs


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

logger = structlog.get_logger()


# OpenAI function calling tool definitions
BOOKING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book an appointment/meeting with the customer on Cal.com. "
                "Use this when the customer agrees to schedule a call, meeting, "
                "or appointment. Parse relative dates like 'tomorrow at 2pm'. "
                "IMPORTANT: You MUST collect the customer's email address and include "
                "it in this call. Ask for email in the same message as confirming the booking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time in HH:MM 24-hour format",
                    },
                    "email": {
                        "type": "string",
                        "description": (
                            "Customer's email address for booking confirmation. "
                            "REQUIRED - always ask for and include the email."
                        ),
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes. Default is 30.",
                        "default": 30,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the appointment",
                    },
                },
                "required": ["date", "time", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check available time slots on Cal.com for a date range. "
                "Use before booking to confirm slot availability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD (defaults to start)",
                    },
                },
                "required": ["start_date"],
            },
        },
    },
]

# Pending responses waiting for debounce
_pending_responses: dict[str, asyncio.Task[None]] = {}


def _extract_email_from_messages(messages: list[dict[str, str]]) -> str | None:
    """Extract email address from conversation history.

    Searches through messages (newest first) for email addresses.

    Args:
        messages: List of message dicts with 'content' key

    Returns:
        The most recently mentioned email address, or None
    """
    import re

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
    import re

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


def build_text_instructions(
    system_prompt: str,
    language: str = "en-US",
    timezone: str = "America/New_York",
    contact_phone: str | None = None,
    offer_context: str | None = None,
    booking_url: str | None = None,
) -> str:
    """Build instructions for text agent.

    Args:
        system_prompt: The agent's custom system prompt
        language: Language code (e.g., "en-US", "es-ES")
        timezone: Workspace timezone
        contact_phone: The contact's phone number
        offer_context: Optional offer context to include in instructions
        booking_url: Optional Cal.com booking URL to include in instructions

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
    offer_section = f"\n\n[OFFER CONTEXT]\n{offer_context}" if offer_context else ""

    # Add booking instruction if URL is provided
    booking_section = ""
    if booking_url:
        booking_section = (
            f"\n\n[BOOKING AVAILABILITY]\n"
            f"If the user wants to book a meeting or appointment, "
            f"suggest they click here: {booking_url}"
        )

    return f"""[CONTEXT]
Language: {language_name}
Timezone: {timezone}
Current: {current_datetime}
Channel: SMS/Text Message{phone_context}{offer_section}{booking_section}

[RESPONSE RULES]
- Respond ONLY in {language_name}
- All times are in {timezone} timezone
- Keep responses concise - SMS has character limits
- Be conversational but efficient
- Do not use markdown formatting (plain text only)
- NEVER include stage directions or narration like "(pauses)" or "(After a moment)"
- You are a TEXT agent - respond directly without describing your actions
- Say "One moment" instead of "(checking...)" or theatrical descriptions
- You may double-text for natural conversation flow

[OBJECTION HANDLING]
- Listen to the SPECIFIC objection - respond to what they said, not a generic rebuttal
- "Need to talk to spouse/partner": Stay curious - "What do you think they'd say?" or \
"What would make this a no-brainer for you both?"
- Deferral objections: Never give up on first pushback. Seek the real concern behind it
- Follow-up: Use "When should I follow up?" not "Would it be okay if I followed up?"
- Stay persistent but respectful - 2-3 attempts before accepting a hard no

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

    from app.models.contact import Contact
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


async def execute_book_appointment(  # noqa: PLR0911
    agent: Agent,
    conversation: Conversation,
    db: AsyncSession,
    date_str: str,
    time_str: str,
    email: str | None = None,
    duration_minutes: int = 30,
    notes: str | None = None,
    timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Execute the book_appointment tool call.

    Creates a booking on Cal.com and saves the appointment to the database.

    Args:
        agent: The agent with calcom_event_type_id
        conversation: The conversation with contact info
        db: Database session
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format (24-hour)
        email: Customer email address for booking confirmation
        duration_minutes: Duration in minutes
        notes: Optional notes
        timezone: Timezone for the appointment

    Returns:
        Dict with success status and booking details or error message
    """
    log = logger.bind(
        agent_id=str(agent.id),
        conversation_id=str(conversation.id),
        date=date_str,
        time=time_str,
    )

    # Check if Cal.com is configured
    if not agent.calcom_event_type_id:
        log.warning("calcom_not_configured")
        return {
            "success": False,
            "error": "Cal.com event type not configured for this agent",
        }

    if not settings.calcom_api_key:
        log.error("calcom_api_key_missing")
        return {
            "success": False,
            "error": "Cal.com API key not configured",
        }

    # Get contact info
    contact: Contact | None = None
    if conversation.contact_id:
        result = await db.execute(
            select(Contact).where(Contact.id == conversation.contact_id)
        )
        contact = result.scalar_one_or_none()
        log.info("contact_lookup", contact_id=conversation.contact_id, found=contact is not None)
    else:
        log.warning("no_contact_id_on_conversation", conversation_phone=conversation.contact_phone)

    if not contact:
        log.warning(
            "contact_not_found",
            conversation_id=str(conversation.id),
            contact_phone=conversation.contact_phone,
        )
        return {
            "success": False,
            "error": "Contact not found for this conversation",
        }

    # Use provided email or fall back to contact's existing email
    booking_email = email or contact.email

    # If email was provided and contact doesn't have one, update the contact
    if email and not contact.email:
        contact.email = email
        await db.flush()
        log.info(
            "contact_email_updated",
            contact_id=contact.id,
            email=email,
        )

    if not booking_email:
        log.warning(
            "contact_email_missing",
            contact_id=contact.id,
            contact_name=contact.full_name,
            contact_phone=contact.phone_number,
        )
        return {
            "success": False,
            "error": "Email is required for booking. Please ask for their email.",
        }

    # Parse date and time
    try:
        tz = ZoneInfo(timezone)
        appointment_datetime = datetime.strptime(
            f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=tz)
    except ValueError as e:
        log.warning("invalid_datetime", error=str(e))
        return {
            "success": False,
            "error": f"Invalid date/time format: {e}",
        }

    # Create Cal.com booking
    calcom_service = CalComService(settings.calcom_api_key)
    try:
        # Convert to UTC for Cal.com API
        appointment_utc = appointment_datetime.astimezone(UTC)

        # Clean phone number - Cal.com wants E.164 format
        phone = contact.phone_number
        if phone:
            # Remove any non-digit chars except leading +
            cleaned = "".join(c for c in phone if c.isdigit())
            if not phone.startswith("+"):
                cleaned = "1" + cleaned if len(cleaned) == 10 else cleaned
            phone = "+" + cleaned

        booking_result = await calcom_service.create_booking(
            event_type_id=agent.calcom_event_type_id,
            contact_email=booking_email,
            contact_name=contact.full_name or "Customer",
            start_time=appointment_utc,
            duration_minutes=duration_minutes,
            metadata={
                "source": "ai_agent",
                "agent_id": str(agent.id),
                "conversation_id": str(conversation.id),
            },
            timezone=timezone,
            language="en",
            phone_number=phone,
        )

        log.info(
            "calcom_booking_created",
            booking_uid=booking_result.get("uid"),
            booking_id=booking_result.get("id"),
        )

        # Create appointment record in database
        appointment = Appointment(
            workspace_id=conversation.workspace_id,
            contact_id=contact.id,
            agent_id=agent.id,
            scheduled_at=appointment_datetime,
            duration_minutes=duration_minutes,
            status="scheduled",
            service_type="video_call",
            notes=notes,
            calcom_booking_uid=booking_result.get("uid"),
            calcom_booking_id=booking_result.get("id"),
            calcom_event_type_id=agent.calcom_event_type_id,
            sync_status="synced",
            last_synced_at=datetime.now(UTC),
        )
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)

        log.info("appointment_created", appointment_id=appointment.id)

        formatted_time = appointment_datetime.strftime("%A, %B %d at %I:%M %p")
        return {
            "success": True,
            "booking_uid": booking_result.get("uid"),
            "scheduled_at": appointment_datetime.isoformat(),
            "duration_minutes": duration_minutes,
            "message": f"Appointment booked for {formatted_time}",
        }

    except Exception as e:
        log.exception("booking_failed", error=str(e))
        return {
            "success": False,
            "error": f"Failed to create booking: {str(e)}",
        }
    finally:
        await calcom_service.close()


async def execute_check_availability(
    agent: Agent,
    start_date_str: str,
    end_date_str: str | None = None,
    timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Execute the check_availability tool call.

    Fetches available time slots from Cal.com.

    Args:
        agent: The agent with calcom_event_type_id
        start_date_str: Start date in YYYY-MM-DD format
        end_date_str: End date in YYYY-MM-DD format (defaults to start_date)
        timezone: Timezone

    Returns:
        Dict with available slots or error message
    """
    log = logger.bind(
        agent_id=str(agent.id),
        start_date=start_date_str,
        end_date=end_date_str,
        timezone=timezone,
    )

    if not agent.calcom_event_type_id:
        return {
            "success": False,
            "error": "Cal.com event type not configured",
        }

    if not settings.calcom_api_key:
        return {
            "success": False,
            "error": "Cal.com API key not configured",
        }

    try:
        tz = ZoneInfo(timezone)
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=tz
        )
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=tz
            )
        else:
            end_date = start_date.replace(hour=23, minute=59, second=59)

    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid date format: {e}",
        }

    calcom_service = CalComService(settings.calcom_api_key)
    try:
        slots = await calcom_service.get_availability(
            event_type_id=agent.calcom_event_type_id,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )

        log.info("availability_checked", slot_count=len(slots))

        # Format slots for AI consumption with date and time
        formatted_slots = []
        for slot in slots[:15]:  # Limit to 15 slots
            slot_date = slot.get("date", "")
            slot_time = slot.get("time", slot.get("start", ""))
            if slot_date and slot_time:
                # Format as "Monday Jan 6 at 2:00 PM" for better AI understanding
                try:
                    slot_dt = datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
                    formatted = slot_dt.strftime("%A %b %d at %I:%M %p")
                    formatted_slots.append(formatted)
                except ValueError:
                    # Fallback to raw format
                    formatted_slots.append(f"{slot_date} {slot_time}")
            elif slot_time:
                formatted_slots.append(slot_time)

        if not formatted_slots and slots:
            # Fallback: return raw slot data if formatting failed
            log.warning("slot_formatting_fallback", raw_slots=slots[:5])
            formatted_slots = [str(s) for s in slots[:10]]

        return {
            "success": True,
            "available_slots": formatted_slots,
            "slot_count": len(slots),
            "date_range": f"{start_date_str} to {end_date_str or start_date_str}",
        }

    except Exception as e:
        log.exception("availability_check_failed", error=str(e))
        return {
            "success": False,
            "error": f"Failed to check availability: {str(e)}",
        }
    finally:
        await calcom_service.close()


async def handle_tool_calls(
    tool_calls: list[ChatCompletionMessageToolCall],
    agent: Agent,
    conversation: Conversation,
    db: AsyncSession,
    timezone: str = "America/New_York",
) -> list[dict[str, Any]]:
    """Handle tool calls from OpenAI and return results.

    Args:
        tool_calls: List of tool calls from OpenAI response
        agent: The agent
        conversation: The conversation
        db: Database session
        timezone: Timezone for bookings

    Returns:
        List of tool results to send back to OpenAI
    """
    results = []

    for tool_call in tool_calls:
        function_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            arguments = {}

        log = logger.bind(
            tool_call_id=tool_call.id,
            function_name=function_name,
            arguments=arguments,
        )
        log.info("executing_tool_call")

        if function_name == "book_appointment":
            result = await execute_book_appointment(
                agent=agent,
                conversation=conversation,
                db=db,
                date_str=arguments.get("date", ""),
                time_str=arguments.get("time", ""),
                email=arguments.get("email"),
                duration_minutes=arguments.get("duration_minutes", 30),
                notes=arguments.get("notes"),
                timezone=timezone,
            )
        elif function_name == "check_availability":
            result = await execute_check_availability(
                agent=agent,
                start_date_str=arguments.get("start_date", ""),
                end_date_str=arguments.get("end_date"),
                timezone=timezone,
            )
        else:
            result = {"success": False, "error": f"Unknown function: {function_name}"}

        results.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "content": json.dumps(result),
        })

        log.info("tool_call_completed", success=result.get("success", False))

    return results


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
        # Get current date for relative date parsing
        try:
            tz = ZoneInfo(timezone)
            now = datetime.now(tz)
            current_date = now.strftime("%Y-%m-%d")
        except Exception:
            current_date = datetime.now().strftime("%Y-%m-%d")

        # Extract email from conversation history
        extracted_email = _extract_email_from_messages(messages)
        email_context = ""
        if extracted_email:
            email_context = f"""
KNOWN EMAIL: The customer has provided their email: {extracted_email}
- Use this email when calling book_appointment
- Do NOT ask for email again - you already have it
- Proceed directly with booking when they confirm a time"""

        booking_instructions = f"""

[APPOINTMENT BOOKING]
Today's date is {current_date}.
{email_context}

CRITICAL RULES - NEVER VIOLATE THESE:
1. NEVER say "one moment", "let me check", or "checking" - just call the function
2. NEVER promise to do something without IMMEDIATELY calling the function
3. If you need availability info, call check_availability IN THIS RESPONSE
4. If user picks a time, call book_appointment IN THIS RESPONSE
5. EMAIL IS REQUIRED - collect email BEFORE or WITH the booking confirmation

EMAIL COLLECTION:
- If you already have the customer's email (see KNOWN EMAIL above), use it directly
- If no email is known, ask for it when offering time slots
- Example: "I have Monday 2pm or Tuesday 10am. Which works? What email for confirmation?"
- Once you have both time AND email, call book_appointment immediately

WHEN TO CALL check_availability:
- User asks about availability ("when", "what times", "what's open")
- User mentions a day ("Monday", "tomorrow", "next week")
- User wants to schedule/book/meet
- You need to offer time options

WHEN TO CALL book_appointment:
- User confirms a specific time AND you have their email (known or just provided)
- ALWAYS include the email parameter when calling book_appointment
- If KNOWN EMAIL exists above, use it immediately when user confirms time

RESPONSE PATTERN:
1. Call the function FIRST (check_availability or book_appointment)
2. THEN respond based on the function result
3. Offer exactly 2 specific time options when presenting availability
4. If no known email, ask for email in the SAME message as time options

FUNCTION FORMATS:
- check_availability: start_date as YYYY-MM-DD (check 3-5 days ahead if not specified)
- book_appointment: date as YYYY-MM-DD, time as HH:MM (24-hour format), email (REQUIRED)

EXAMPLES:
✓ "when are you free?" → check_availability → "Monday 2pm or Tuesday 10am. What email?"
✓ "Monday, email is john@example.com" → book_appointment(email) → "Booked! Sent to john@"
✓ "Monday works" (with known email) → book_appointment(known_email) → "Booked!"
✓ "Monday works" (no known email) → "Great! What email should I send the confirmation to?"

The ONLY way to check times is check_availability. The ONLY way to book is book_appointment."""

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
            api_params["tools"] = BOOKING_TOOLS
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

            # Execute the tool calls
            tool_results = await handle_tool_calls(
                tool_calls=assistant_message.tool_calls,
                agent=agent,
                conversation=conversation,
                db=db,
                timezone=timezone,
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


# Follow-up message generation system prompt
FOLLOWUP_SYSTEM_PROMPT = """You are a friendly, professional follow-up assistant. Your job is to \
re-engage contacts who haven't responded recently. Write a short, conversational follow-up message.

RULES:
1. Be warm and human - not pushy or salesy
2. Reference the conversation context naturally
3. Keep it SHORT (1-3 sentences max)
4. Ask an open-ended question or offer value
5. Don't repeat the same approach if there were previous follow-ups
6. Respect their time - acknowledge they may be busy
7. No pressure tactics or guilt trips
8. Plain text only - no markdown or emojis

GOOD EXAMPLES:
- "Hey {first_name}, just checking in - any questions I can help with?"
- "Hi! I know things get busy. Still interested in chatting?"
- "Following up - would a quick call work better for you?"

BAD EXAMPLES:
- "URGENT: Last chance to respond!" (too pushy)
- "I noticed you haven't replied..." (guilt trip)
- "Did you get my last message?" (annoying)"""


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
