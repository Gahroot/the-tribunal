"""Text/SMS prompt builder for AI text agents.

This module provides prompt construction for SMS/text conversations,
similar to VoicePromptBuilder but optimized for the text channel.

Key differences from voice:
- No telephony guidance (it's SMS, not a call)
- Character limit awareness
- No realism cues (text doesn't need [sigh], [laugh])
- Includes booking URL option as alternative to function calling

Usage:
    from app.services.ai.text_prompt_builder import build_text_instructions

    instructions = build_text_instructions(
        system_prompt=agent.system_prompt,
        language="en-US",
        timezone="America/New_York",
        contact_phone="+15551234567",
        offer_context="Customer was offered 20% off...",
    )
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Language code to name mapping
LANGUAGE_NAMES = {
    "en-US": "English",
    "es-ES": "Spanish",
    "es-MX": "Mexican Spanish",
    "fr-FR": "French",
    "de-DE": "German",
    "pt-BR": "Brazilian Portuguese",
}


def build_text_instructions(
    system_prompt: str,
    language: str = "en-US",
    timezone: str = "America/New_York",
    contact_phone: str | None = None,
    offer_context: str | None = None,
    booking_url: str | None = None,
) -> str:
    """Build instructions for text agent.

    Constructs the complete system prompt with context, rules, and
    objection handling guidelines for SMS conversations.

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
    language_name = LANGUAGE_NAMES.get(language, language)

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


def build_booking_instructions(
    timezone: str = "America/New_York",
    extracted_email: str | None = None,
) -> str:
    """Build booking-specific instructions for text agents with function calling.

    Args:
        timezone: Workspace timezone for date context
        extracted_email: Email extracted from conversation history

    Returns:
        Booking instructions to append to system prompt
    """
    # Get current date for relative date parsing
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        current_date = now.strftime("%Y-%m-%d")
    except Exception:
        current_date = datetime.now().strftime("%Y-%m-%d")

    # Email context if known
    email_context = ""
    if extracted_email:
        email_context = f"""
KNOWN EMAIL: The customer has provided their email: {extracted_email}
- Use this email when calling book_appointment
- Do NOT ask for email again - you already have it
- Proceed directly with booking when they confirm a time"""

    return f"""

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
- "when are you free?" -> check_availability -> "Monday 2pm or Tuesday 10am. What email?"
- "Monday, email is john@example.com" -> book_appointment(email) -> "Booked! Sent to john@"
- "Monday works" (with known email) -> book_appointment(known_email) -> "Booked!"
- "Monday works" (no known email) -> "Great! What email should I send the confirmation to?"

The ONLY way to check times is check_availability. The ONLY way to book is book_appointment."""


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
