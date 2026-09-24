"""Voice agent tool definitions.

This module consolidates tool definitions that were previously scattered
across multiple voice agent implementations. Provides:
- DTMF tool for IVR navigation
- Cal.com booking tools with dynamic date context
- Grok built-in tools (web_search, x_search)

Usage:
    from app.services.ai.voice_tools import get_booking_tools, DTMF_TOOL

    tools = get_booking_tools(timezone="America/New_York")
    if dtmf_enabled:
        tools.append(DTMF_TOOL)
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from app.services.ai.tool_definition import ToolFormat
from app.services.ai.tool_definitions import TOOL_DEFINITIONS

logger = structlog.get_logger()

# Grok built-in tools - these execute automatically on the provider side
GROK_BUILTIN_TOOLS: dict[str, dict[str, str]] = {
    "web_search": {
        "type": "web_search",
    },
    "x_search": {
        "type": "x_search",
    },
}

# Only a live, matching appointment reconfirmation call may execute this tool.
CONFIRM_APPOINTMENT_TOOL: dict[str, Any] = TOOL_DEFINITIONS["confirm_appointment"].render("grok")

# DTMF tool for IVR menu navigation
# Allows AI agent to send touch-tone digits during calls
DTMF_TOOL: dict[str, Any] = TOOL_DEFINITIONS["send_dtmf"].render("grok")

# Live transfer / handoff tool.
# Briefs a configured human closer on high intent. A live handoff additionally
# requires the caller's explicit consent and the closer's keypad acceptance.
# The execution layer always uses warm mode and resolves the destination.
TRANSFER_CALL_TOOL: dict[str, Any] = TOOL_DEFINITIONS["transfer_call"].render("grok")

# On-demand knowledge retrieval tool.
# Replaces static prompt-stuffing (the old ~4k-token CAG concat): instead of
# dumping the whole knowledge base into the system prompt, the agent calls this
# tool to pull only the passages it needs for the current question. Execution
# runs hybrid (vector + keyword) retrieval scoped to the call's workspace + agent.
SEARCH_KNOWLEDGE_TOOL: dict[str, Any] = TOOL_DEFINITIONS["search_knowledge"].render("grok")

# Read-only caller account lookup tool.
# Lets the receptionist answer account-specific questions about the *current
# caller* ("when's my appointment?", "what's my status?") by reading only that
# caller's own CRM record. Execution is strictly read-only and hard-scoped to the
# call's workspace + resolved contact, so it can never read another tenant's or
# another person's data. Takes no arguments — the caller is implicit (the active
# call), so the model cannot point it at a different contact.
LOOKUP_CALLER_RECORD_TOOL: dict[str, Any] = TOOL_DEFINITIONS["lookup_caller_record"].render("grok")

# "Take a message" capture tool.
# Lets the receptionist capture a structured message for a human when the
# caller wants someone to call them back or to relay something — instead of
# transferring or booking. The execution layer persists the message and
# notifies operators (push + email). Opt-in via ``take_message`` in the agent's
# enabled_tools so it is only exposed on receptionist-style agents.
TAKE_MESSAGE_TOOL: dict[str, Any] = TOOL_DEFINITIONS["take_message"].render("grok")

# In-call payment / deposit collection tool.
# SECURE BY DESIGN: this NEVER reads raw card numbers over the AI channel. The
# execution layer creates a Stripe Checkout Session for the requested amount and
# texts the hosted payment link to the caller, recording payment intent/status
# against the contact/opportunity. Opt-in via ``collect_payment`` in the agent's
# enabled_tools so only agents authorized to take money expose it.
COLLECT_PAYMENT_TOOL: dict[str, Any] = TOOL_DEFINITIONS["collect_payment"].render("grok")

# Companion read-only tool: lets the agent confirm whether the most recent
# in-call payment link has been paid yet. Read-only (no spend, no mutation of
# external state) so it is gate-exempt and safe to poll during the live call.
CHECK_PAYMENT_STATUS_TOOL: dict[str, Any] = TOOL_DEFINITIONS["check_payment_status"].render("grok")

APPLICATION_LINK_SMS_TOOL: dict[str, Any] = TOOL_DEFINITIONS["send_application_link"].render("grok")

# Static booking tool definitions (without date context)
# Use get_booking_tools() for tools with embedded date context
VOICE_BOOKING_TOOLS: list[dict[str, Any]] = [
    TOOL_DEFINITIONS[name].render("grok")
    for name in ("book_appointment", "check_availability", "hold_booking_slot", "booking_recovery")
]


def _booking_tools(provider: ToolFormat, timezone: str) -> list[dict[str, Any]]:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        logger.debug("invalid_timezone_fallback", timezone=timezone)
        tz = ZoneInfo("America/New_York")
    now = datetime.now(tz)
    today_str = now.strftime("%A, %B %d, %Y")
    today_iso = now.strftime("%Y-%m-%d")
    context = (
        f"TODAY IS {today_str} ({today_iso}). "
        f"Convert relative dates to YYYY-MM-DD from today: 'today' = {today_iso}, "
        "'tomorrow' = the day after today, 'Friday' = the NEXT Friday from today."
    )
    if provider != "openai":
        context += (
            " VOICE FLOW: check_availability -> hold_booking_slot -> collect name and email "
            "-> book_appointment. After interruptions or tangents use booking_recovery to "
            "resume; never start a second booking or claim a hold is confirmed."
        )
    return [
        TOOL_DEFINITIONS[name].render(provider, date_context=context)
        for name in (
            ("book_appointment", "check_availability")
            if provider == "openai"
            else ("book_appointment", "check_availability", "hold_booking_slot", "booking_recovery")
        )
    ]


def get_booking_tools(timezone: str = "America/New_York") -> list[dict[str, Any]]:
    """Render shared booking schemas with timezone-aware date context."""
    return _booking_tools("grok", timezone)


def build_tools_list(
    *,
    enable_booking: bool = False,
    enable_web_search: bool = False,
    enable_x_search: bool = False,
    enable_dtmf: bool = False,
    enable_application_link_sms: bool = False,
    enable_transfer: bool = False,
    enable_search_knowledge: bool = False,
    enable_lookup_caller_record: bool = False,
    enable_take_message: bool = False,
    enable_collect_payment: bool = False,
    timezone: str = "America/New_York",
) -> list[dict[str, Any]]:
    """Build a complete tools list based on enabled features.

    Args:
        enable_booking: Include Cal.com booking tools
        enable_web_search: Include Grok web search tool
        enable_x_search: Include Grok X/Twitter search tool
        enable_dtmf: Include DTMF tool for IVR navigation
        enable_application_link_sms: Include fixed Prestyj application-link SMS tool
        enable_transfer: Include live human transfer/handoff tool
        enable_search_knowledge: Include the on-demand knowledge retrieval tool
        enable_lookup_caller_record: Include the read-only caller record lookup tool
        enable_take_message: Include the "take a message" capture tool
        enable_collect_payment: Include the in-call payment/deposit collection tool
        timezone: Timezone for booking tools date context

    Returns:
        List of tool definitions for session configuration
    """
    tools: list[dict[str, Any]] = [TOOL_DEFINITIONS["confirm_appointment"].render("grok")]

    # Built-in Grok tools
    if enable_web_search:
        tools.append(GROK_BUILTIN_TOOLS["web_search"])

    if enable_x_search:
        tools.append(GROK_BUILTIN_TOOLS["x_search"])

    # On-demand knowledge retrieval (replaces static CAG prompt-stuffing)
    if enable_search_knowledge:
        tools.append(TOOL_DEFINITIONS["search_knowledge"].render("grok"))

    # Read-only lookup of the current caller's own CRM record
    if enable_lookup_caller_record:
        tools.append(TOOL_DEFINITIONS["lookup_caller_record"].render("grok"))

    # Structured "take a message" capture for operator follow-up
    if enable_take_message:
        tools.append(TOOL_DEFINITIONS["take_message"].render("grok"))

    # In-call payment / deposit collection (secure SMS link + status check)
    if enable_collect_payment:
        tools.append(TOOL_DEFINITIONS["collect_payment"].render("grok"))
        tools.append(TOOL_DEFINITIONS["check_payment_status"].render("grok"))

    # DTMF for IVR
    if enable_dtmf:
        tools.append(TOOL_DEFINITIONS["send_dtmf"].render("grok"))
        tools.append(TOOL_DEFINITIONS["navigate_booking_menu"].render("grok"))

    # Live human transfer / handoff
    if enable_transfer:
        tools.append(TOOL_DEFINITIONS["transfer_call"].render("grok"))

    # Fixed Prestyj application-link SMS
    if enable_application_link_sms:
        tools.append(TOOL_DEFINITIONS["send_application_link"].render("grok"))

    # Booking tools with date context
    if enable_booking:
        tools.extend(get_booking_tools(timezone))

    return tools


def is_transfer_enabled(agent: Any) -> bool:
    """Return whether the live transfer/handoff tool should be exposed.

    Transfer is opt-in: the agent must enable it (either a direct
    ``"transfer_call"`` entry in ``enabled_tools`` or the integration-based
    ``call_control`` + ``transfer_call`` pattern) AND have a destination number
    resolvable (per-agent ``transfer_destination_number`` here; the executor
    additionally falls back to workspace settings at call time).
    """
    if not agent:
        return False

    enabled_tools = agent.enabled_tools or []
    tool_settings = agent.tool_settings or {}
    call_control_tools = tool_settings.get("call_control", []) or []
    return "transfer_call" in enabled_tools or (
        "call_control" in enabled_tools and "transfer_call" in call_control_tools
    )


def get_tools_from_agent_config(
    agent: Any,
    *,
    enable_booking: bool = False,
    timezone: str = "America/New_York",
) -> list[dict[str, Any]]:
    """Build tools list from agent configuration.

    Reads the agent's enabled_tools and tool_settings to determine
    which tools to include.

    Args:
        agent: Agent model with enabled_tools and tool_settings
        enable_booking: Whether Cal.com booking is available
        timezone: Timezone for booking tools date context

    Returns:
        List of tool definitions
    """
    if not agent:
        return []

    enabled_tools = agent.enabled_tools or []
    tool_settings = agent.tool_settings or {}

    # Check for DTMF enablement
    # Supports both direct "send_dtmf" in enabled_tools (legacy)
    # and integration-based "call_control" with "send_dtmf" in tool_settings
    call_control_tools = tool_settings.get("call_control", []) or []
    dtmf_enabled = "send_dtmf" in enabled_tools or (
        "call_control" in enabled_tools and "send_dtmf" in call_control_tools
    )

    # This is intentionally opt-in. The function sends a fixed Prestyj link,
    # so a generic "twilio_send_sms" setting must not expose it to every agent.
    twilio_sms_tools = tool_settings.get("twilio-sms", []) or []
    application_link_sms_enabled = "send_application_link" in enabled_tools or (
        "twilio-sms" in enabled_tools and "send_application_link" in twilio_sms_tools
    )

    return build_tools_list(
        enable_booking=enable_booking,
        enable_web_search="web_search" in enabled_tools,
        enable_x_search="x_search" in enabled_tools,
        enable_dtmf=dtmf_enabled,
        enable_application_link_sms=application_link_sms_enabled,
        enable_transfer=is_transfer_enabled(agent),
        enable_search_knowledge=is_search_knowledge_enabled(agent),
        enable_lookup_caller_record=is_lookup_caller_record_enabled(agent),
        enable_take_message=is_take_message_enabled(agent),
        enable_collect_payment=is_collect_payment_enabled(agent),
        timezone=timezone,
    )


def is_search_knowledge_enabled(agent: Any) -> bool:
    """Return whether the on-demand knowledge retrieval tool should be exposed.

    Opt-in via ``"search_knowledge"`` in the agent's ``enabled_tools``. The tool
    is only useful when the agent has an ingested knowledge base, so operators
    enable it explicitly rather than paying the per-turn tool overhead always.
    """
    if not agent:
        return False
    return "search_knowledge" in (agent.enabled_tools or [])


def is_lookup_caller_record_enabled(agent: Any) -> bool:
    """Return whether the read-only caller record lookup tool should be exposed.

    Opt-in via ``"lookup_caller_record"`` in the agent's ``enabled_tools``. The
    tool reads the caller's own CRM record (appointments, deals, status), so
    operators enable it explicitly for receptionist-style agents rather than
    exposing account data on every agent by default.
    """
    if not agent:
        return False
    return "lookup_caller_record" in (agent.enabled_tools or [])


def is_collect_payment_enabled(agent: Any) -> bool:
    """Return whether the in-call payment/deposit collection tool should be exposed.

    Opt-in via ``"collect_payment"`` in the agent's ``enabled_tools``. The tool
    initiates real money movement (a Stripe payment link texted to the caller),
    so it is enabled explicitly for agents authorized to take payments rather
    than exposed on every agent by default.
    """
    if not agent:
        return False
    return "collect_payment" in (agent.enabled_tools or [])


def is_take_message_enabled(agent: Any) -> bool:
    """Return whether the "take a message" capture tool should be exposed.

    Opt-in via ``"take_message"`` in the agent's ``enabled_tools``. The tool
    persists a structured message and notifies operators, so it is enabled
    explicitly for receptionist-style agents rather than on every agent.
    """
    if not agent:
        return False
    return "take_message" in (agent.enabled_tools or [])


# Grok available voices (for validation)
GROK_VOICES: dict[str, str] = {
    "ara": "Ara - Warm & friendly (female, default)",
    "rex": "Rex - Confident & clear (male)",
    "sal": "Sal - Smooth & balanced (neutral)",
    "eve": "Eve - Energetic & upbeat (female)",
    "leo": "Leo - Authoritative & strong (male)",
}


def validate_grok_voice(voice_id: str) -> str | None:
    """Validate and normalize a Grok voice ID.

    Args:
        voice_id: Voice ID to validate

    Returns:
        Capitalized voice name if valid, None if invalid
    """
    voice_lower = voice_id.lower()
    if voice_lower in GROK_VOICES:
        return voice_lower.capitalize()
    return None


# OpenAI function calling format (for text agents)
# These use the {"type": "function", "function": {...}} wrapper
def get_text_search_knowledge_tool() -> dict[str, Any]:
    """Render the shared knowledge tool for OpenAI chat completions."""
    return TOOL_DEFINITIONS["search_knowledge"].render("openai")


def get_text_booking_tools(timezone: str = "America/New_York") -> list[dict[str, Any]]:
    """Render the shared booking schemas for OpenAI chat completions."""
    return _booking_tools("openai", timezone)
