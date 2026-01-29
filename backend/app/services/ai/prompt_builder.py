"""Voice prompt builder for consistent prompt engineering.

This module consolidates all prompt construction logic that was previously
duplicated across voice agent implementations. It provides a single source
of truth for:
- Date context injection
- Identity prefix
- Realism cues (Grok)
- Search guidance
- Telephony guidance
- Booking instructions

Usage:
    builder = VoicePromptBuilder(agent, timezone="America/New_York")
    prompt = builder.build_full_prompt(
        base_prompt=agent.system_prompt,
        include_realism=True,
        include_booking=True,
        is_outbound=False,
    )
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models.agent import Agent


class VoicePromptBuilder:
    """Builder for voice agent system prompts.

    Consolidates all prompt engineering patterns used across voice agents
    to eliminate duplication and ensure consistency.

    Features:
    - Date context injection for appointment booking accuracy
    - Agent identity prefix for consistent identification
    - Realism cues for Grok voice expressiveness
    - Search tools guidance for web/X search
    - Telephony behavior guidance
    - Cal.com booking instructions

    Attributes:
        agent: Optional Agent model for configuration
        timezone: Timezone for date context (IANA format)
    """

    def __init__(
        self,
        agent: Agent | None = None,
        timezone: str = "America/New_York",
    ) -> None:
        """Initialize prompt builder.

        Args:
            agent: Optional Agent model for configuration
            timezone: Timezone for date context (IANA format)
        """
        self.agent = agent
        self.timezone = timezone
        self._tz = self._get_timezone()

    def _get_timezone(self) -> ZoneInfo:
        """Get ZoneInfo for configured timezone.

        Returns:
            ZoneInfo object, defaulting to America/New_York on error
        """
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("America/New_York")

    def get_date_context(self) -> str:
        """Get date context string for system prompt.

        Critical for appointment booking accuracy - LLMs often have
        outdated training data dates.

        Returns:
            Date context string to prepend to prompts
        """
        now = datetime.now(self._tz)
        today_str = now.strftime("%A, %B %d, %Y")
        today_iso = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%I:%M %p")

        return (
            f"CRITICAL DATE CONTEXT: Today is {today_str} ({today_iso}). "
            f"The current time is {current_time}. "
            f"Your training data may be outdated - ALWAYS use {today_iso} as today's date.\n\n"
        )

    def get_identity_prefix(self) -> str:
        """Get identity prefix for agent name enforcement.

        Returns:
            Identity instruction string, or empty if no agent name
        """
        if not self.agent or not self.agent.name:
            return ""

        agent_name = self.agent.name
        return (
            f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
            f"You MUST always identify yourself as {agent_name}. "
            f"When greeting or introducing yourself, say your name is {agent_name}. "
            "This is non-negotiable.\n\n"
        )

    def get_realism_cues(self) -> str:
        """Get Grok realism enhancement instructions.

        These cues allow the voice to use auditory expressions
        for more natural conversation.

        Returns:
            Realism instructions string
        """
        return """
# Voice Realism Enhancements
You can use these auditory cues naturally in your responses to sound more human:
- [sigh] - Express mild frustration, relief, or thoughtfulness
- [laugh] - React to humor or express friendliness
- [whisper] - For confidential or emphasis moments
- Use these sparingly and naturally - don't overuse them.
"""

    def get_search_guidance(self) -> str:
        """Get search tools guidance based on agent configuration.

        Returns:
            Search tools instructions if any are enabled, empty otherwise
        """
        if not self.agent or not self.agent.enabled_tools:
            return ""

        enabled = self.agent.enabled_tools
        has_web_search = "web_search" in enabled
        has_x_search = "x_search" in enabled

        if not has_web_search and not has_x_search:
            return ""

        parts = ["\n\n# Search Capabilities"]

        if has_web_search:
            parts.append(
                "You have access to real-time web search. "
                "Use it when users ask about current events, prices, news, weather, "
                "facts you're unsure about, or anything that requires up-to-date information. "
                "Search results are integrated automatically - respond naturally."
            )

        if has_x_search:
            parts.append(
                "You have access to X (Twitter) search. "
                "Use it when users ask about trending topics, public opinions, "
                "what people are saying about something, or recent posts. "
                "The search results will help you provide current social context."
            )

        if has_web_search or has_x_search:
            parts.append(
                "Use these search tools proactively when the conversation would benefit "
                "from current information - don't wait to be asked explicitly."
            )

        return "\n".join(parts)

    def get_telephony_guidance(self, is_outbound: bool = False) -> str:
        """Get telephony-specific behavior guidance.

        Args:
            is_outbound: True if this is an outbound call

        Returns:
            Telephony guidance string
        """
        if is_outbound:
            return """

IMPORTANT: You are on a phone call that YOU initiated.
- You called THEM - introduce yourself and explain why you're calling
- Do NOT ask "what would you like to talk about" - YOU know why you called
- Be direct and professional about the purpose of your call"""
        else:
            return """

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally and wait for response
- Do NOT generate random content, fun facts, or filler - stay focused on your purpose
- Speak clearly and conversationally as if on a real phone call"""

    def get_booking_instructions(self) -> str:
        """Get Cal.com booking instructions with current date context.

        Returns:
            Booking instructions string with embedded date context
        """
        now = datetime.now(self._tz)
        today_str = now.strftime("%A, %B %d, %Y")
        today_iso = now.strftime("%Y-%m-%d")

        return f"""

[APPOINTMENT BOOKING - CRITICAL DATE AND RULES]
TODAY IS {today_str} ({today_iso}).
Your training data may be outdated - IGNORE IT. The ACTUAL current date is {today_iso}.

When converting relative dates to YYYY-MM-DD format:
- "today" = {today_iso}
- "tomorrow" = the day after {today_iso}
- "Friday" = the NEXT Friday from {today_iso} (calculate it)
- "next week" = the week starting after {today_iso}
- "Monday" = the NEXT Monday from {today_iso}

You have tools to check calendar availability and book appointments. Follow these rules:

1. NEVER say "one moment", "let me check", "checking", or "I'll get back to you"
2. NEVER promise to do something without IMMEDIATELY calling the function
3. When the customer asks about times, call check_availability RIGHT NOW
4. When the customer picks a time, call book_appointment RIGHT NOW
5. EMAIL IS REQUIRED for booking - ask for it when offering time slots

WHEN TO CALL check_availability:
- Customer asks about availability ("when are you free", "what times work")
- Customer mentions a day ("Monday", "tomorrow", "next week", "Friday")
- Customer wants to schedule or book something
- ALWAYS use dates relative to {today_iso}, NOT your training data dates

WHEN TO CALL book_appointment:
- Customer confirms a specific time AND you have their email

RESPONSE PATTERN:
- If they ask about times: Call check_availability, then offer 2 specific options
- If they pick a time and you have email: Call book_appointment immediately
- If they pick a time but no email: Ask for email, then book once provided

DO NOT say things like "I'll check and get back to you" - you can check instantly!"""

    def build_context_section(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
        is_outbound: bool = False,
    ) -> str:
        """Build call context section for system prompt.

        Args:
            contact_info: Contact information dict
            offer_info: Offer/product information dict
            is_outbound: True if this is an outbound call

        Returns:
            Context section string
        """
        if not contact_info and not offer_info:
            return ""

        parts = []
        parts.extend(self._build_call_direction_header(is_outbound))

        if contact_info:
            parts.extend(self._build_contact_section(contact_info, is_outbound))

        if offer_info:
            parts.extend(self._build_offer_section(offer_info, is_outbound))

        return "\n".join(parts)

    def _build_call_direction_header(self, is_outbound: bool) -> list[str]:
        """Build header section based on call direction."""
        if is_outbound:
            return [
                "\n\n# CURRENT CALL CONTEXT - THIS IS AN OUTBOUND CALL YOU ARE MAKING",
                "You initiated this call. You know exactly why you're calling. "
                "Do NOT ask the customer what they want to talk about.",
            ]
        return [
            "\n\n# CURRENT CALL CONTEXT - THIS IS AN INBOUND CALL",
            "The customer called you. Listen to what they need and assist them.",
        ]

    def _build_contact_section(
        self, contact_info: dict[str, Any], is_outbound: bool
    ) -> list[str]:
        """Build contact information section."""
        header = "\n## Customer You Are Calling:" if is_outbound else "\n## Customer Information:"
        parts = [header]
        if contact_info.get("name"):
            parts.append(f"- Name: {contact_info['name']}")
        if contact_info.get("company"):
            parts.append(f"- Company: {contact_info['company']}")
        return parts

    def _build_offer_section(
        self, offer_info: dict[str, Any], is_outbound: bool
    ) -> list[str]:
        """Build offer information section."""
        header = "\n## What You Are Calling About:" if is_outbound else "\n## Offer Information:"
        parts = [header]
        if offer_info.get("name"):
            parts.append(f"- Offer: {offer_info['name']}")
        if offer_info.get("description"):
            parts.append(f"- Details: {offer_info['description']}")
        if offer_info.get("terms"):
            parts.append(f"- Terms: {offer_info['terms']}")
        return parts

    def build_full_prompt(
        self,
        base_prompt: str | None = None,
        *,
        include_date_context: bool = True,
        include_identity: bool = True,
        include_realism: bool = False,
        include_search: bool = True,
        include_telephony: bool = True,
        include_booking: bool = False,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
        is_outbound: bool = False,
    ) -> str:
        """Build complete system prompt with all enhancements.

        Args:
            base_prompt: Base system prompt (defaults to agent.system_prompt)
            include_date_context: Include date context section
            include_identity: Include identity prefix
            include_realism: Include realism cues (Grok only)
            include_search: Include search guidance
            include_telephony: Include telephony guidance
            include_booking: Include booking instructions
            contact_info: Contact information for context
            offer_info: Offer information for context
            is_outbound: True if outbound call

        Returns:
            Complete enhanced system prompt
        """
        # Get base prompt
        if base_prompt is None:
            base_prompt = (
                self.agent.system_prompt
                if self.agent
                else "You are a helpful AI voice assistant."
            )

        parts = []

        # 1. Date context (FIRST - critical for booking)
        if include_date_context:
            parts.append(self.get_date_context())

        # 2. Identity prefix
        if include_identity:
            parts.append(self.get_identity_prefix())

        # 3. Base prompt
        parts.append(base_prompt)

        # 4. Call context
        context = self.build_context_section(contact_info, offer_info, is_outbound)
        if context:
            parts.append(context)

        # 5. Realism cues (Grok)
        if include_realism:
            parts.append(self.get_realism_cues())

        # 6. Search guidance
        if include_search:
            parts.append(self.get_search_guidance())

        # 7. Booking instructions
        if include_booking:
            parts.append(self.get_booking_instructions())

        # 8. Telephony guidance (last)
        if include_telephony:
            parts.append(self.get_telephony_guidance(is_outbound))

        return "".join(parts)

    def get_outbound_opener_prompt(self) -> str:
        """Get the pattern interrupt opener prompt for outbound calls.

        Returns:
            Prompt text for triggering outbound call opener
        """
        # Extract just the first name
        full_name = self.agent.name if self.agent else "Alex"
        agent_name = full_name.split("|")[0].split("-")[0].strip().split()[0]

        return (
            f"You just called someone. Open with a pattern interrupt. "
            f"Say: 'Hey! It's {agent_name}. This is a sales call. "
            f"Do you wanna hang up... or can I tell you why I'm calling?!' "
            f"Start friendly and upbeat. Sound a bit disappointed on 'hang up'. "
            f"Then get excited on 'or can I tell you why I'm calling?!' "
            f"Wait for their response."
        )

    def get_inbound_greeting_prompt(self, greeting: str | None = None) -> str:
        """Get the greeting prompt for inbound calls.

        Args:
            greeting: Optional specific greeting text

        Returns:
            Prompt text for triggering inbound greeting
        """
        if greeting:
            return f"Greet the caller by saying: {greeting}"

        # Build default greeting prompt
        parts = []

        if self.agent and self.agent.name:
            parts.append(f"You are {self.agent.name}.")

        parts.append(
            "Greet the caller and introduce yourself. Follow your "
            "system instructions for the purpose of this call."
        )

        return " ".join(parts)
