"""Canonical agent tool definitions.

Edit a tool's argument model and definition HERE, never a provider payload.
Provider exports and text validation are derived from these same models.
CRM approval/confirmation execution remains in crm_assistant._tool_metadata.
"""

from types import MappingProxyType
from typing import Any, Literal

from pydantic import Field

from app.services.ai.tool_definition import ToolArguments, ToolChannel, ToolDefinition


class ConfirmAppointmentArguments(ToolArguments):
    caller_quote: str = Field(description="The caller's exact affirmative words (e.g. 'yes').")


class SendDtmfArguments(ToolArguments):
    digits: str = Field(
        description=(
            "The digit(s) to press. MUST include at least one digit (0-9, *, #). "
            "Examples: '1' (press 1), '2' (press 2), '0' (operator), '#' (pound key). For"
            " multiple digits with pauses: '1w2' (press 1, wait 0.5s, press 2). "
            "IMPORTANT: Do not send only 'w' - always include actual digits."
        )
    )


class TransferQualificationArguments(ToolArguments):
    budget: str | None = Field(default=None)
    authority: str | None = Field(default=None)
    need: str | None = Field(default=None)
    timeline: str | None = Field(default=None)
    objections: str | None = Field(default=None)


class TransferCallArguments(ToolArguments):
    reason: str = Field(
        description=(
            "Short reason for the handoff, e.g. 'caller asked for a human', 'hot lead "
            "ready to buy', or 'frustrated about billing'."
        )
    )
    intent: str | None = Field(
        default=None,
        description=(
            "One short phrase describing what the caller wants — spoken to the human in "
            "warm mode (e.g. 'wants pricing on the premium plan')."
        ),
    )
    summary: str | None = Field(
        default=None, description="Brief factual summary of what the caller said on this call."
    )
    caller_consented: bool = Field(
        description="True only after explicit agreement to speak with a human now."
    )
    consent_quote: str | None = Field(
        default=None, description="The caller's actual words agreeing to speak to a human now."
    )
    qualification: TransferQualificationArguments | None = Field(
        default=None, description="Facts the caller gave during this call, not guesses."
    )


class SearchKnowledgeArguments(ToolArguments):
    query: str = Field(
        description=(
            "What you need to find out, phrased as a focused question or keywords (e.g. "
            "'cancellation policy for monthly plan', 'weekend opening hours')."
        ),
        min_length=1,
    )
    top_k: int | None = Field(
        default=None,
        description=(
            "Optional number of passages to retrieve (1-10). Defaults to 5. Ask for more "
            "only when a broad question needs several sources."
        ),
        ge=1,
        le=10,
    )


class LookupCallerRecordArguments(ToolArguments):
    pass


class TakeMessageArguments(ToolArguments):
    caller_name: str | None = Field(
        default=None, description="The caller's name (who the message is from)."
    )
    callback_number: str | None = Field(
        default=None,
        description=(
            "The best phone number to call the caller back on. Read it back to confirm "
            "before sending."
        ),
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Short reason or topic for the message (e.g. 'billing question', 'wants a "
            "quote', 'following up on order')."
        ),
    )
    urgency: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description=(
            "How urgent the callback is. Use 'high' only when the caller says it's "
            "urgent/time-sensitive."
        ),
    )
    preferred_callback_time: str | None = Field(
        default=None,
        description=(
            "When the caller would prefer to be called back, in their own words (e.g. "
            "'tomorrow afternoon', 'after 5pm', 'anytime')."
        ),
    )
    message: str = Field(description="The full free-text message the caller wants relayed.")


class CollectPaymentArguments(ToolArguments):
    amount: float = Field(
        description=(
            "The amount to charge in the major currency unit (e.g. dollars). For example "
            "50 means $50.00. Must be a positive number you have confirmed with the "
            "caller."
        )
    )
    description: str | None = Field(
        default=None,
        description=(
            "Short description of what the payment is for, e.g. 'booking deposit', "
            "'invoice #1234'. Shown to the caller on the payment page."
        ),
    )
    currency: str | None = Field(
        default=None,
        description=(
            "Optional ISO 4217 currency code (e.g. 'usd', 'gbp'). Defaults to USD when omitted."
        ),
    )


class CheckPaymentStatusArguments(ToolArguments):
    pass


class SendApplicationLinkArguments(ToolArguments):
    pass


class HoldBookingSlotArguments(ToolArguments):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class BookingRecoveryArguments(ToolArguments):
    action: Literal["status", "off_script", "resume", "change_slot", "cancel"]


class NavigateBookingMenuArguments(ToolArguments):
    transcript: str = Field(min_length=1, max_length=4000)
    goal: Literal["book", "human", "repeat", "back"] = "book"


class BookAppointmentArguments(ToolArguments):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="The caller's stated name; required for voice booking.",
    )
    date: str = Field(description="Appointment date in YYYY-MM-DD format", min_length=1)
    time: str = Field(
        description=(
            "Appointment time in HH:MM 24-hour format (e.g., '14:00' for 2 PM, '09:30' "
            "for 9:30 AM). Always pass 24-hour format here even though you speak 12-hour "
            "format to the customer."
        ),
        min_length=1,
    )
    email: str = Field(
        description="Customer's email address for booking confirmation", min_length=1
    )
    duration_minutes: int = Field(
        default=30, description="Duration in minutes. Default is 30.", ge=1
    )
    notes: str | None = Field(default=None, description="Optional notes about the appointment")
    skill: str | None = Field(
        default=None,
        description=(
            "Optional skill, specialty, or service the appointment needs (e.g. 'spanish',"
            " 'mortgage', 'new car sales'). When set, the system routes the booking to an"
            " available staff member who has that skill. Only pass this if the caller's "
            "need clearly maps to a specialty; otherwise leave it out."
        ),
    )


class CheckAvailabilityArguments(ToolArguments):
    start_date: str = Field(description="Start date in YYYY-MM-DD format", min_length=1)
    end_date: str | None = Field(
        default=None, description="End date in YYYY-MM-DD (defaults to start)"
    )
    skill: str | None = Field(
        default=None,
        description=(
            "Optional skill/specialty needed; restricts availability to staff with that "
            "skill when skill-based routing is enabled."
        ),
    )


class GetContactTimelineArguments(ToolArguments):
    contact_id: int


class RecordContactNoteArguments(ToolArguments):
    contact_id: int
    note: str


class SearchContactsArguments(ToolArguments):
    query: str = Field(description="Search term")
    limit: int | None = Field(default=None, description="Max results (default 10)")


class CreateContactArguments(ToolArguments):
    first_name: str
    last_name: str | None = Field(default=None)
    phone: str = Field(description="E.164 format (+15551234567)")
    email: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class ListCampaignsArguments(ToolArguments):
    status: str | None = Field(
        default=None, description="draft | scheduled | running | paused | completed | canceled"
    )
    limit: int | None = Field(default=None, description="Max results (default 10)")


class ListAgentsArguments(ToolArguments):
    limit: int | None = Field(default=None, description="Max results (default 10)")


class SendSmsArguments(ToolArguments):
    contact_id: int
    body: str = Field(description="Message text")


class SendInitialMessageArguments(ToolArguments):
    campaign_id: str = Field(description="Campaign UUID")
    contact_id: int


class StartCampaignArguments(ToolArguments):
    campaign_id: str = Field(description="Campaign UUID")


class PauseCampaignArguments(ToolArguments):
    campaign_id: str = Field(description="Campaign UUID")


class ResumeCampaignArguments(ToolArguments):
    campaign_id: str = Field(description="Campaign UUID")


class SummarizeCampaignArguments(ToolArguments):
    campaign_id: str = Field(description="Campaign UUID")


class PlanOutboundGrowthWorkflowArguments(ToolArguments):
    intent: str | None = Field(default=None, description="User's outbound goal in plain English")
    offer_id: str | None = Field(default=None, description="Offer UUID, if already chosen")
    segment_id: str | None = Field(default=None, description="Segment UUID, if already chosen")
    from_phone_number: str | None = Field(default=None, description="Sending phone number in E.164")
    create_draft: bool | None = Field(
        default=None, description="Create draft campaign now (default true)"
    )
    create_responder_agent: bool | None = Field(
        default=None, description="Create inactive responder draft if no active responder exists"
    )


class CreateAgentArguments(ToolArguments):
    name: str
    description: str | None = Field(default=None)
    channel_mode: str | None = Field(default=None, description="voice | text | both")
    voice_provider: str | None = Field(default=None, description="openai | elevenlabs")
    voice_id: str | None = Field(default=None)
    language: str | None = Field(default=None)
    system_prompt: str
    temperature: float | None = Field(default=None)
    enabled_tools: list[str] | None = Field(default=None)


class UpdateAgentArguments(ToolArguments):
    agent_id: str = Field(description="Agent UUID")
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    channel_mode: str | None = Field(default=None, description="voice | text | both")
    system_prompt: str | None = Field(default=None)
    temperature: float | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    enabled_tools: list[str] | None = Field(default=None)


class AssignAiResponderArguments(ToolArguments):
    conversation_id: str = Field(description="Conversation UUID")
    agent_id: str = Field(description="Agent UUID")
    ai_enabled: bool | None = Field(default=None)


class GetConversationArguments(ToolArguments):
    contact_id: int
    limit: int | None = Field(default=None, description="Recent messages (default 20)")


class ListRecentConversationsArguments(ToolArguments):
    limit: int | None = Field(default=None, description="Max results (default 10)")


class ListAppointmentsArguments(ToolArguments):
    limit: int | None = Field(default=None, description="Max results (default 10)")


class GetDashboardStatsArguments(ToolArguments):
    pass


class GetTodayQueueArguments(ToolArguments):
    pass


class ListOpportunitiesArguments(ToolArguments):
    limit: int | None = Field(default=None, description="Max results (default 10)")


class ListOffersArguments(ToolArguments):
    active_only: bool | None = Field(default=None, description="Only return active offers")
    limit: int | None = Field(default=None, description="Max results (default 10)")


class GetOfferDetailsArguments(ToolArguments):
    offer_id: str = Field(description="Offer UUID")


class OfferValueStackItemArguments(ToolArguments):
    name: str
    description: str | None = Field(default=None)
    value: float
    included: bool | None = Field(default=None)


class CreateOfferDraftArguments(ToolArguments):
    name: str
    description: str | None = Field(default=None)
    discount_type: str | None = Field(default=None, description="percentage | fixed | free_service")
    discount_value: float | None = Field(default=None)
    terms: str | None = Field(default=None)
    headline: str | None = Field(default=None)
    subheadline: str | None = Field(default=None)
    regular_price: float | None = Field(default=None)
    offer_price: float | None = Field(default=None)
    savings_amount: float | None = Field(default=None)
    guarantee_type: str | None = Field(
        default=None, description="money_back | satisfaction | results"
    )
    guarantee_days: int | None = Field(default=None)
    guarantee_text: str | None = Field(default=None)
    urgency_type: str | None = Field(
        default=None, description="limited_time | limited_quantity | expiring"
    )
    urgency_text: str | None = Field(default=None)
    scarcity_count: int | None = Field(default=None)
    value_stack_items: list[OfferValueStackItemArguments] | None = Field(default=None)
    package_options: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Structured package ladder; each item includes key, ad_count, price, "
            "problems_covered, cost_per_ad, and role."
        ),
    )
    negotiation_sequence: list[dict[str, Any]] | None = Field(
        default=None, description="Ordered anchor/fallback/upsell sales strategy steps."
    )
    strategy_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional autonomous-sales strategy metadata and escalation rules.",
    )
    cta_text: str | None = Field(default=None)
    cta_subtext: str | None = Field(default=None)


class CreateCheckoutLinkArguments(ToolArguments):
    pack_key: str = Field(
        description=(
            "Batch pack key: sampler_100 (100 ads / $497), growth_300 (300 ads / $1497), "
            "anchor_500 (500 ads / $2500), scale_1000 (1,000 ads / $3997)."
        )
    )
    contact_id: int = Field(description="The buyer's contact id")
    currency: str | None = Field(
        default=None, description="Optional ISO 4217 currency code; defaults to USD"
    )


class UpdateOfferDraftArguments(ToolArguments):
    offer_id: str = Field(description="Offer UUID")
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    discount_type: str | None = Field(default=None, description="percentage | fixed | free_service")
    discount_value: float | None = Field(default=None)
    terms: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    headline: str | None = Field(default=None)
    subheadline: str | None = Field(default=None)
    regular_price: float | None = Field(default=None)
    offer_price: float | None = Field(default=None)
    savings_amount: float | None = Field(default=None)
    guarantee_type: str | None = Field(
        default=None, description="money_back | satisfaction | results"
    )
    guarantee_days: int | None = Field(default=None)
    guarantee_text: str | None = Field(default=None)
    urgency_type: str | None = Field(
        default=None, description="limited_time | limited_quantity | expiring"
    )
    urgency_text: str | None = Field(default=None)
    scarcity_count: int | None = Field(default=None)
    value_stack_items: list[OfferValueStackItemArguments] | None = Field(default=None)
    package_options: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Structured package ladder; each item includes key, ad_count, price, "
            "problems_covered, cost_per_ad, and role."
        ),
    )
    negotiation_sequence: list[dict[str, Any]] | None = Field(
        default=None, description="Ordered anchor/fallback/upsell sales strategy steps."
    )
    strategy_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional autonomous-sales strategy metadata and escalation rules.",
    )
    cta_text: str | None = Field(default=None)
    cta_subtext: str | None = Field(default=None)


_DEFINITIONS = (
    ToolDefinition(
        name="confirm_appointment",
        description=(
            "Only on an appointment reconfirmation call, record the caller's explicit yes"
            " to attending. Do not use for voicemail, uncertain answers, or rescheduling."
        ),
        arguments=ConfirmAppointmentArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="send_dtmf",
        description=(
            "Send DTMF touch-tone digits to navigate automated phone menus (IVR systems)."
            " CRITICAL: When you hear 'Press 1 for X, Press 2 for Y', you MUST use this "
            "tool to send the appropriate digit - do NOT speak to the machine. Choose the"
            " menu option that best matches your goal (e.g., '2' for 'new car sales'). If"
            " the menu option for your goal isn't clear, try options 1-9 systematically. "
            "Only try '0' or '#' as a last resort after other options have failed. After "
            "sending DTMF, WAIT SILENTLY for either another menu or a human to answer. "
            "Only speak when a real human responds to you."
        ),
        arguments=SendDtmfArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="transfer_call",
        description=(
            "Brief a human closer when the caller shows high intent or BANT-qualifies. "
            "Ask if they want to speak to a human now before transferring. Set "
            "caller_consented true ONLY after an explicit yes or direct request to speak "
            "to the human. Otherwise this only briefs the closer and the AI stays on the "
            "call. Never infer consent from intent or frustration. While the human hears "
            "the briefing and confirms availability, keep assisting the caller. The AI "
            "audio stops automatically when the human accepts."
        ),
        arguments=TransferCallArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="search_knowledge",
        description=(
            "Search this business's knowledge base for facts you need to answer the "
            "caller accurately — pricing, policies, FAQs, hours, product details, or "
            "anything specific to this company. Call this BEFORE answering any factual "
            "question instead of guessing. Pass a focused natural-language query "
            "describing what you need to know. Returns ranked passages with the document "
            "title each came from; ground your answer in those passages and do NOT invent"
            " details that are not returned."
        ),
        arguments=SearchKnowledgeArguments,
        channels=frozenset(("voice", "text")),
        gate_exempt=True,
    ),
    ToolDefinition(
        name="lookup_caller_record",
        description=(
            "Look up the CURRENT caller's own account record to answer questions about "
            "THEIR appointments, status, or deals — e.g. 'when is my appointment?', "
            "'what's my status?', 'do I have anything booked?'. Returns the caller's "
            "upcoming appointments, open opportunities/deals, contact status and notes, "
            "and a short summary of the last interaction. This is READ-ONLY and only ever"
            " returns THIS caller's record — you cannot look up anyone else. If the "
            "caller is not recognized it returns no record; in that case, do NOT invent "
            "details — offer to take their information instead. Takes no arguments."
        ),
        arguments=LookupCallerRecordArguments,
        channels=frozenset(("voice",)),
        gate_exempt=True,
    ),
    ToolDefinition(
        name="take_message",
        description=(
            "Take a message for a human team member when the caller wants someone to call"
            " them back or to relay information — and you cannot resolve it yourself or "
            "transfer/book. Collect as much structure as the caller will give: their "
            "name, the best callback number, the reason/topic, how urgent it is, when "
            "they'd prefer to be called back, and the message itself. Confirm the "
            "callback number back to the caller before sending. Call this ONCE you have "
            "gathered the details; the team is notified immediately. Do not invent "
            "details the caller did not give — leave fields out instead."
        ),
        arguments=TakeMessageArguments,
        channels=frozenset(("voice",)),
        # Capture and notify only: approval would stall the caller's message.
        gate_exempt=True,
    ),
    ToolDefinition(
        name="collect_payment",
        description=(
            "Collect a payment or deposit from the CURRENT caller by texting them a "
            "secure payment link. Use this ONLY after the caller explicitly agrees to pay"
            " a specific amount (e.g. a booking deposit or invoice). NEVER ask the caller"
            " to read out their card number, CVV, or expiry — you do NOT take card "
            "details by voice. This tool sends a secure Stripe link by SMS to the "
            "caller's phone; they complete payment there. Confirm the amount and what it "
            "is for before calling this. After calling it, tell the caller to check their"
            " phone for the payment link, and use check_payment_status if they say "
            "they've paid."
        ),
        arguments=CollectPaymentArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="check_payment_status",
        description=(
            "Check whether the payment link you just texted the CURRENT caller has been "
            "paid. Call this when the caller says they have completed (or are having "
            "trouble with) the payment. Takes no arguments — it checks this call's most "
            "recent payment request. Do not invent a result; report only what this tool "
            "returns."
        ),
        arguments=CheckPaymentStatusArguments,
        channels=frozenset(("voice",)),
        gate_exempt=True,
    ),
    ToolDefinition(
        name="send_application_link",
        description=(
            "Send the fixed Prestyj founding cohort application link by SMS to the "
            "current caller. Use only after the person explicitly agrees to receive the "
            "link. The SMS body is fixed; do not use this for general texting, custom "
            "follow-ups, or unrelated links."
        ),
        arguments=SendApplicationLinkArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="hold_booking_slot",
        description=(
            "After the caller selects a returned slot, hold it before collecting their name and "
            "email. A hold is not a confirmed booking. Never invent a slot."
        ),
        arguments=HoldBookingSlotArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="booking_recovery",
        description=(
            "Inspect booking status after interruptions. "
            "Use off_script for a tangent, then resume. "
            "Only use change_slot or cancel when explicitly requested by the caller. "
            "Never retry an uncertain calendar operation."
        ),
        arguments=BookingRecoveryArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="navigate_booking_menu",
        description=(
            "Navigate an external phone menu from its latest heard transcript, "
            "e.g. press 1 to book. "
            "Send tones, not spoken digits. Wait for the next menu after each step. "
            "This does not book or confirm an appointment."
        ),
        arguments=NavigateBookingMenuArguments,
        channels=frozenset(("voice",)),
    ),
    ToolDefinition(
        name="book_appointment",
        description=(
            "Book an appointment/meeting with the customer on Cal.com. Use this when the "
            "customer agrees to schedule a call, meeting, or appointment. You MUST "
            "collect the customer's email address first."
        ),
        arguments=BookAppointmentArguments,
        channels=frozenset(("voice", "text")),
    ),
    ToolDefinition(
        name="check_availability",
        description=(
            "Check available time slots on Cal.com for a date range. Use before booking "
            "to confirm slot availability."
        ),
        arguments=CheckAvailabilityArguments,
        channels=frozenset(("voice", "text")),
    ),
    ToolDefinition(
        name="get_contact_timeline",
        description="Read a contact's shared voice, SMS, campaign and CRM history.",
        arguments=GetContactTimelineArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="record_contact_note",
        description="Record a contact fact, subject to workspace approval rules.",
        arguments=RecordContactNoteArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="search_contacts",
        description="Search contacts by name, phone, email, or company.",
        arguments=SearchContactsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="create_contact",
        description="Create a new contact. Requires first_name + phone in E.164.",
        arguments=CreateContactArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_campaigns",
        description="List campaigns. Filter by status if provided.",
        arguments=ListCampaignsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_agents",
        description="List AI agents in the workspace.",
        arguments=ListAgentsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="send_sms",
        description=(
            "Send an SMS to a contact by id. Confirm with the user first unless they "
            "already gave a clear directive."
        ),
        arguments=SendSmsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="send_initial_message",
        description=(
            "Send a campaign's initial message to one contact. Requires explicit confirmation."
        ),
        arguments=SendInitialMessageArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="start_campaign",
        description=(
            "Start a draft, paused, or scheduled campaign. This can send messages or "
            "calls; requires explicit user confirmation."
        ),
        arguments=StartCampaignArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="pause_campaign",
        description="Pause a running campaign. Does not send messages or calls.",
        arguments=PauseCampaignArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="resume_campaign",
        description=(
            "Resume a paused campaign. This can immediately send messages or calls; "
            "requires explicit user confirmation."
        ),
        arguments=ResumeCampaignArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="summarize_campaign",
        description="Summarize campaign status, delivery, replies, appointments, and rates.",
        arguments=SummarizeCampaignArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="plan_outbound_growth_workflow",
        description=(
            "Turn a high-level outbound intent into offer/segment selection, campaign "
            "copy, sample previews, a draft campaign, responder recommendation, and next "
            "approval step."
        ),
        arguments=PlanOutboundGrowthWorkflowArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="create_agent",
        description="Create a new AI agent. Requires explicit confirmation.",
        arguments=CreateAgentArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="update_agent",
        description="Update an existing AI agent. Requires explicit confirmation.",
        arguments=UpdateAgentArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="assign_ai_responder",
        description=(
            "Assign an AI agent to respond in a conversation. Requires explicit confirmation."
        ),
        arguments=AssignAiResponderArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="get_conversation",
        description="Read recent messages with a contact.",
        arguments=GetConversationArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_recent_conversations",
        description="Show recent conversations across all contacts.",
        arguments=ListRecentConversationsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_appointments",
        description="Show upcoming appointments.",
        arguments=ListAppointmentsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="get_dashboard_stats",
        description="Current totals: contacts, campaigns, conversations, upcoming appointments.",
        arguments=GetDashboardStatsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="get_today_queue",
        description=(
            "Today's ordered mission queue: pending approvals, nudges due today, fresh "
            "ad-library prospect batches, draft campaigns awaiting launch, and setup "
            "gaps. Use for morning briefings and 'what should I do today?'."
        ),
        arguments=GetTodayQueueArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_opportunities",
        description="Pipeline opportunities/deals.",
        arguments=ListOpportunitiesArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="list_offers",
        description="List offer drafts and active offers for outbound campaigns.",
        arguments=ListOffersArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="get_offer_details",
        description="Get full offer details for campaign messaging or review.",
        arguments=GetOfferDetailsArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="create_offer_draft",
        description="Create an inactive offer draft suitable for outbound campaign copy.",
        arguments=CreateOfferDraftArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="create_checkout_link",
        description=(
            "Close a Prestyj Batch Video Ads deal: generate a secure Stripe Checkout link"
            " for the chosen pack and text it to the buyer over iMessage. Use ONLY after "
            "the buyer agrees to buy a specific batch pack. The price is fixed "
            "server-side by pack_key — never invent an amount. Do NOT use this for "
            "add-ons beyond the batch (running ads, installing AI agents, consulting); "
            "those must be escalated to a human."
        ),
        arguments=CreateCheckoutLinkArguments,
        channels=frozenset(("crm",)),
    ),
    ToolDefinition(
        name="update_offer_draft",
        description="Update an offer draft before attaching it to outbound campaigns.",
        arguments=UpdateOfferDraftArguments,
        channels=frozenset(("crm",)),
    ),
)

TOOL_DEFINITIONS = MappingProxyType({tool.name: tool for tool in _DEFINITIONS})
if len(TOOL_DEFINITIONS) != len(_DEFINITIONS):
    raise ValueError("Duplicate agent tool name")


def tools_for_channel(channel: ToolChannel) -> tuple[ToolDefinition, ...]:
    """Return definitions, preserving the established provider ordering."""
    return tuple(tool for tool in _DEFINITIONS if channel in tool.channels)


def gate_exempt_tools(channel: ToolChannel) -> frozenset[str]:
    """Only explicitly exempt tools bypass approval; unknown names never do."""
    return frozenset(tool.name for tool in tools_for_channel(channel) if tool.gate_exempt)
