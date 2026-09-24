"""Operator-reviewed starter kits for consented, inbound-lead follow-up.

Catalog assets only: not automatically enabled campaigns or legal approval.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerticalKit:
    name: str
    audience: str
    offer: str
    qualification: tuple[str, ...]
    voice_script: str
    initial_sms: str
    follow_up_sms: str
    objections: tuple[tuple[str, str], ...]
    proof_assets: tuple[str, ...]
    compliance_addendum: tuple[str, ...]


SHARED_RULES = (
    "Use only documented, permitted leads; check consent, opt-outs, calling hours "
    "and suppression lists before any outreach.",
    "Disclose the AI assistant and business identity; never impersonate a person "
    "or fabricate availability, results, discounts or testimonials.",
    "Honor STOP and other opt-outs immediately. Obtain recording consent where required.",
    "Have the operator approve scripts, campaign settings and local rules before launch.",
)


VERTICAL_KITS: dict[str, VerticalKit] = {
    "real_estate": VerticalKit(
        name="Real estate inquiry response",
        audience="Brokerages and agents following up on property inquiries",
        offer="Qualify opted-in buyer/seller inquiries and request an agent meeting.",
        qualification=(
            "Buyer or seller intent and target area",
            "Timeline and preferred contact method",
            "Agent coverage and confirmed meeting slot",
        ),
        voice_script=(
            "Hello, this is the AI assistant for your real estate team, following up "
            "on your property inquiry. Is now a good time? Are you looking to buy, "
            "sell, or just exploring? Which area and timeline matter to you? "
            "If you'd like, I can check a time with an agent."
        ),
        initial_sms=(
            "Hi {first_name}, following up on your property inquiry. Want to talk "
            "with an agent? Reply STOP to opt out."
        ),
        follow_up_sms=(
            "Hi {first_name}, checking in once about your property inquiry. "
            "Still looking for help? Reply STOP to opt out."
        ),
        objections=(
            ("Just browsing", "No pressure. Would a market overview help?"),
            ("Already have an agent", "Understood. I won't pursue a meeting."),
            (
                "What is my home worth?",
                "An agent can review comparable sales; "
                "I can't promise a price without reviewing the property.",
            ),
        ),
        proof_assets=(
            "Permissioned anonymized inquiry-to-meeting funnel with dates",
            "Agent-approved redacted sample follow-up transcript",
            "Attendance report and lead-source breakdown",
        ),
        compliance_addendum=(
            "Use brokerage-approved fair-housing language; never steer or infer protected traits.",
            "Check representation status; route legal, financing and valuation advice "
            "to licensed professionals.",
            "Verify local brokerage identification and advertising requirements.",
        ),
    ),
    "roofing": VerticalKit(
        name="Roofing estimate inquiry response",
        audience="Roofing contractors following up on requested estimates",
        offer="Qualify opted-in estimate requests and request an inspection slot.",
        qualification=(
            "Property location and decision-maker",
            "Repair/replacement need and urgency",
            "Service area and confirmed inspection slot",
        ),
        voice_script=(
            "Hello, this is the AI assistant for your roofing team, following up "
            "on your estimate request. Is now a good time? Is this a repair or "
            "replacement, and what area is the property in? I can check an "
            "inspection time; a contractor will assess the work and pricing."
        ),
        initial_sms=(
            "Hi {first_name}, following up on your roofing estimate request. "
            "Want an inspection? Reply STOP to opt out."
        ),
        follow_up_sms=(
            "Hi {first_name}, one check-in on your roofing request. "
            "Still need an inspection? Reply STOP to opt out."
        ),
        objections=(
            ("How much?", "A contractor needs to inspect the roof before quoting."),
            ("Insurance will pay", "Your insurer decides coverage; we can't promise approval."),
            (
                "It's an emergency",
                "If there's immediate danger, follow local emergency "
                "guidance. I'll flag the urgency rather than promise a slot.",
            ),
        ),
        proof_assets=(
            "Redacted estimate-request to inspection funnel by source",
            "Permissioned work examples with scope and date",
            "Attendance and estimate-acceptance report from contractor records",
        ),
        compliance_addendum=(
            "Never promise insurance payouts or diagnose storm damage without inspection.",
            "Verify licensing, permits and solicitation rules before advertising or quoting.",
            "Do not call an inspection free without approved terms.",
        ),
    ),
    "hvac": VerticalKit(
        name="HVAC service inquiry response",
        audience="HVAC contractors following up on requested service",
        offer="Triage opted-in service requests and request a technician visit.",
        qualification=(
            "Service address and equipment type",
            "Symptoms, urgency and decision-maker",
            "Service area and confirmed technician slot",
        ),
        voice_script=(
            "Hello, this is the AI assistant for your HVAC team, following up "
            "on your service request. Is now a good time? Is this heating or "
            "cooling, and what symptoms are you seeing? I can check a technician "
            "visit; the technician will diagnose and quote any work."
        ),
        initial_sms=(
            "Hi {first_name}, following up on your HVAC service request. "
            "Want help scheduling a visit? Reply STOP to opt out."
        ),
        follow_up_sms=(
            "Hi {first_name}, one check-in on your HVAC request. "
            "Still need a technician? Reply STOP to opt out."
        ),
        objections=(
            (
                "Can you diagnose it by phone?",
                "I can record symptoms, but a technician "
                "must assess the system before diagnosing or quoting.",
            ),
            (
                "Can you come today?",
                "I'll check the schedule; I can't promise same-day service until confirmed.",
            ),
            (
                "It smells like gas",
                "Leave the area and contact your gas utility "
                "or emergency services immediately; don't wait for an appointment.",
            ),
        ),
        proof_assets=(
            "Redacted request-to-completed-visit funnel",
            "Permissioned technician follow-up example without customer details",
            "Dated booking, attendance and job outcome summary",
        ),
        compliance_addendum=(
            "Escalate gas smells or carbon monoxide alarms to emergency guidance.",
            "Never diagnose, quote or guarantee savings before a technician evaluates it.",
            "Confirm technician licensing and local advertising rules before publication.",
        ),
    ),
}


def get_vertical_kit(vertical: str) -> VerticalKit:
    """Return an immutable operator-facing kit by stable vertical key."""
    return VERTICAL_KITS[vertical]


def get_vertical_campaign_copy(vertical: str) -> dict[str, str]:
    """Return fields accepted by Campaign creation; never schedule sends here.

    Caller must verify permission, identify the actual business in copy, and set
    workspace, agent, phone, sending hours and suppression rules separately.
    """
    kit = get_vertical_kit(vertical)
    return {
        "name": kit.name,
        "initial_message": kit.initial_sms,
        "follow_up_message": kit.follow_up_sms,
    }
