"""Lead qualification service using AI to extract signals from conversations.

Implements BANT framework (Budget, Authority, Need, Timeline) for lead qualification
and automated lead scoring based on conversation analysis.
"""

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation, Message

logger = structlog.get_logger()

# Lead scoring weights
SCORING_WEIGHTS = {
    "budget_detected": 25,
    "authority_detected": 20,
    "need_detected": 20,
    "timeline_detected": 15,
    "interest_high": 15,
    "interest_medium": 8,
    "appointment_booked": 20,
    "response_rate_bonus": 10,  # If contact responds frequently
    "pain_point_per": 3,  # Per pain point identified (max 5)
}

# Qualification threshold
QUALIFICATION_THRESHOLD = 60  # Score >= 60 = qualified


EXTRACTION_SYSTEM_PROMPT = """You are a lead qualification analyst. \
Analyze the conversation and extract qualification signals using the BANT framework.

Extract the following from the conversation:

1. **Budget** - Any mention of budget, pricing concerns, affordability, cost expectations
2. **Authority** - Signs the contact is a decision maker or needs approval from others
3. **Need** - The specific problems, pain points, or needs they've expressed
4. **Timeline** - Any urgency, deadlines, or timeframes mentioned

Also identify:
- **Interest Level**: high (eager, ready to proceed), medium (interested but cautious), \
low (minimal engagement), unknown
- **Pain Points**: Specific problems they want to solve
- **Objections**: Concerns or hesitations they've raised
- **Next Steps**: Any agreed upon or suggested next actions

Respond ONLY with valid JSON matching this exact structure:
{
    "budget": {
        "detected": boolean,
        "value": "extracted budget info or null",
        "confidence": 0.0-1.0
    },
    "authority": {
        "detected": boolean,
        "value": "role/authority info or null",
        "confidence": 0.0-1.0
    },
    "need": {
        "detected": boolean,
        "value": "summarized need or null",
        "confidence": 0.0-1.0
    },
    "timeline": {
        "detected": boolean,
        "value": "timeline info or null",
        "confidence": 0.0-1.0
    },
    "interest_level": "high|medium|low|unknown",
    "pain_points": ["pain point 1", "pain point 2"],
    "objections": ["objection 1", "objection 2"],
    "next_steps": "suggested next step or null"
}"""


async def get_conversation_transcript(
    contact_id: int,
    db: AsyncSession,
    max_messages: int = 100,
) -> tuple[str, int]:
    """Get all conversation messages for a contact.

    Args:
        contact_id: The contact ID
        db: Database session
        max_messages: Maximum messages to retrieve per conversation

    Returns:
        Tuple of (formatted transcript, conversation count)
    """
    # Use selectinload to eager load messages (2 queries instead of 1+N)
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.contact_id == contact_id)
    )
    conversations = result.scalars().all()

    if not conversations:
        return "", 0

    transcript_parts = []
    conversation_count = len(conversations)

    for conversation in conversations:
        # Messages already loaded via selectinload
        # Sort and limit in Python (acceptable since building full transcript)
        messages = sorted(
            conversation.messages,
            key=lambda m: m.created_at
        )[:max_messages]

        for msg in messages:
            direction = "Contact" if msg.direction == "inbound" else "Agent"
            content = msg.body or msg.transcript or "[No content]"
            transcript_parts.append(f"{direction}: {content}")

    return "\n".join(transcript_parts), conversation_count


async def extract_qualification_signals(
    transcript: str,
    openai_api_key: str,
) -> dict[str, Any]:
    """Extract qualification signals from conversation transcript using AI.

    Args:
        transcript: The conversation transcript
        openai_api_key: OpenAI API key

    Returns:
        Extracted qualification signals dict
    """
    log = logger.bind(transcript_length=len(transcript))

    if not transcript.strip():
        log.info("empty_transcript")
        return _empty_signals()

    client = AsyncOpenAI(api_key=openai_api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Analyze this conversation and extract qualification signals:"
                        f"\n\n{transcript}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            log.warning("empty_response")
            return _empty_signals()

        signals: dict[str, Any] = json.loads(content)
        log.info("signals_extracted", interest_level=signals.get("interest_level"))
        return signals

    except json.JSONDecodeError as e:
        log.error("json_parse_error", error=str(e))
        return _empty_signals()
    except Exception as e:
        log.exception("extraction_error", error=str(e))
        return _empty_signals()


def _empty_signals() -> dict[str, Any]:
    """Return empty qualification signals structure."""
    return {
        "budget": {"detected": False, "value": None, "confidence": 0.0},
        "authority": {"detected": False, "value": None, "confidence": 0.0},
        "need": {"detected": False, "value": None, "confidence": 0.0},
        "timeline": {"detected": False, "value": None, "confidence": 0.0},
        "interest_level": "unknown",
        "pain_points": [],
        "objections": [],
        "next_steps": None,
    }


def calculate_lead_score(
    signals: dict[str, Any],
    has_appointment: bool = False,
    response_rate: float = 0.0,
) -> int:
    """Calculate lead score based on qualification signals.

    Args:
        signals: Qualification signals dict
        has_appointment: Whether contact has booked an appointment
        response_rate: Contact's response rate (0.0-1.0)

    Returns:
        Lead score (0-100)
    """
    score = 0

    # BANT signals
    if signals.get("budget", {}).get("detected"):
        confidence = signals["budget"].get("confidence", 0.5)
        score += int(SCORING_WEIGHTS["budget_detected"] * confidence)

    if signals.get("authority", {}).get("detected"):
        confidence = signals["authority"].get("confidence", 0.5)
        score += int(SCORING_WEIGHTS["authority_detected"] * confidence)

    if signals.get("need", {}).get("detected"):
        confidence = signals["need"].get("confidence", 0.5)
        score += int(SCORING_WEIGHTS["need_detected"] * confidence)

    if signals.get("timeline", {}).get("detected"):
        confidence = signals["timeline"].get("confidence", 0.5)
        score += int(SCORING_WEIGHTS["timeline_detected"] * confidence)

    # Interest level
    interest = signals.get("interest_level", "unknown")
    if interest == "high":
        score += SCORING_WEIGHTS["interest_high"]
    elif interest == "medium":
        score += SCORING_WEIGHTS["interest_medium"]

    # Pain points (max 5 counted)
    pain_points = signals.get("pain_points", [])
    score += min(len(pain_points), 5) * SCORING_WEIGHTS["pain_point_per"]

    # Appointment bonus
    if has_appointment:
        score += SCORING_WEIGHTS["appointment_booked"]

    # Response rate bonus (if they respond to >50% of messages)
    if response_rate > 0.5:
        score += int(SCORING_WEIGHTS["response_rate_bonus"] * response_rate)

    return min(score, 100)


async def check_has_appointment(contact_id: int, db: AsyncSession) -> bool:
    """Check if contact has any appointments.

    Args:
        contact_id: The contact ID
        db: Database session

    Returns:
        True if contact has appointments
    """
    from app.models.appointment import Appointment

    result = await db.execute(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.contact_id == contact_id)
    )
    count = result.scalar() or 0
    return count > 0


async def calculate_response_rate(contact_id: int, db: AsyncSession) -> float:
    """Calculate contact's response rate.

    Args:
        contact_id: The contact ID
        db: Database session

    Returns:
        Response rate (0.0-1.0)
    """
    # Single query with conditional aggregation (1 query instead of 3)
    result = await db.execute(
        select(
            func.sum(
                case(
                    (Message.direction == "outbound", 1),
                    else_=0
                )
            ).label("outbound_count"),
            func.sum(
                case(
                    (Message.direction == "inbound", 1),
                    else_=0
                )
            ).label("inbound_count"),
        )
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.contact_id == contact_id)
    )

    row = result.first()

    if not row:
        return 0.0

    outbound_count = row.outbound_count or 0
    inbound_count = row.inbound_count or 0

    if outbound_count == 0:
        return 0.0

    # Response rate = inbound responses / outbound messages (capped at 1.0)
    return min(inbound_count / outbound_count, 1.0)


async def analyze_and_qualify_contact(
    contact_id: int,
    db: AsyncSession,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Analyze contact conversations and update qualification status.

    Args:
        contact_id: The contact ID
        db: Database session
        openai_api_key: Optional OpenAI API key (uses settings if not provided)

    Returns:
        Dict with qualification results
    """
    log = logger.bind(contact_id=contact_id)
    log.info("analyzing_contact")

    api_key = openai_api_key or settings.openai_api_key
    if not api_key:
        log.error("no_openai_api_key")
        return {"success": False, "error": "OpenAI API key not configured"}

    # Get contact
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        log.error("contact_not_found")
        return {"success": False, "error": "Contact not found"}

    # Get conversation transcript
    transcript, conversation_count = await get_conversation_transcript(contact_id, db)

    if not transcript:
        log.info("no_conversations")
        return {
            "success": True,
            "lead_score": 0,
            "is_qualified": False,
            "message": "No conversations to analyze",
        }

    # Extract qualification signals
    signals = await extract_qualification_signals(transcript, api_key)

    # Add metadata
    signals["last_analyzed_at"] = datetime.now(UTC).isoformat()
    signals["conversation_count"] = conversation_count

    # Check for appointment and response rate
    has_appointment = await check_has_appointment(contact_id, db)
    response_rate = await calculate_response_rate(contact_id, db)

    # Calculate lead score
    lead_score = calculate_lead_score(signals, has_appointment, response_rate)

    # Determine qualification status
    is_qualified = lead_score >= QUALIFICATION_THRESHOLD

    # Update contact
    contact.qualification_signals = signals
    contact.lead_score = lead_score
    was_qualified = contact.is_qualified
    contact.is_qualified = is_qualified

    # Set qualified_at timestamp if newly qualified
    if is_qualified and not was_qualified:
        contact.qualified_at = datetime.now(UTC)
        # Auto-update status to qualified if still new/contacted
        if contact.status in ("new", "contacted"):
            contact.status = "qualified"

    await db.commit()
    await db.refresh(contact)

    log.info(
        "contact_qualified",
        lead_score=lead_score,
        is_qualified=is_qualified,
        interest_level=signals.get("interest_level"),
    )

    return {
        "success": True,
        "contact_id": contact_id,
        "lead_score": lead_score,
        "is_qualified": is_qualified,
        "qualification_signals": signals,
        "has_appointment": has_appointment,
        "response_rate": response_rate,
    }


async def batch_analyze_contacts(
    workspace_id: str,
    db: AsyncSession,
    limit: int = 50,
) -> dict[str, Any]:
    """Analyze multiple contacts in a workspace.

    Prioritizes contacts that haven't been analyzed or were analyzed long ago.

    Args:
        workspace_id: Workspace UUID
        db: Database session
        limit: Maximum contacts to analyze

    Returns:
        Summary of batch analysis results
    """
    log = logger.bind(workspace_id=workspace_id)

    api_key = settings.openai_api_key
    if not api_key:
        return {"success": False, "error": "OpenAI API key not configured"}

    # Get contacts that need analysis (never analyzed or analyzed >24h ago)
    from sqlalchemy import text

    result = await db.execute(
        select(Contact)
        .where(
            Contact.workspace_id == workspace_id,
            Contact.status.in_(["new", "contacted"]),
        )
        .order_by(
            # Prioritize never-analyzed contacts
            text("qualification_signals IS NULL DESC"),
            Contact.updated_at.desc(),
        )
        .limit(limit)
    )
    contacts = result.scalars().all()

    log.info("batch_analysis_started", contact_count=len(contacts))

    analyzed = 0
    qualified = 0
    errors = 0
    contact_results: list[dict[str, Any]] = []

    for contact in contacts:
        try:
            analysis = await analyze_and_qualify_contact(contact.id, db, api_key)
            if analysis.get("success"):
                analyzed += 1
                if analysis.get("is_qualified"):
                    qualified += 1
                contact_results.append({
                    "contact_id": contact.id,
                    "lead_score": analysis.get("lead_score"),
                    "is_qualified": analysis.get("is_qualified"),
                })
            else:
                errors += 1
        except Exception as e:
            log.error("contact_analysis_failed", contact_id=contact.id, error=str(e))
            errors += 1

    log.info(
        "batch_analysis_completed",
        analyzed=analyzed,
        qualified=qualified,
        errors=errors,
    )

    return {
        "success": True,
        "analyzed": analyzed,
        "qualified": qualified,
        "errors": errors,
        "contacts": contact_results,
    }
