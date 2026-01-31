"""Public demo endpoints for landing page."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select

from app.api.deps import DB
from app.core.config import settings
from app.core.utils import get_client_ip
from app.models.contact import Contact
from app.models.demo_request import DemoRequest
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.telephony.telnyx_voice import TelnyxVoiceService

router = APIRouter()


class DemoCallRequest(BaseModel):
    """Request to trigger a demo call."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        # Remove all non-digit characters
        digits = "".join(c for c in v if c.isdigit())

        # Validate US number (10 or 11 digits)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)


class DemoTextRequest(BaseModel):
    """Request to trigger a demo text."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        # Remove all non-digit characters
        digits = "".join(c for c in v if c.isdigit())

        # Validate US number (10 or 11 digits)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)


class DemoResponse(BaseModel):
    """Response from demo request."""

    success: bool
    message: str


class LeadSubmitRequest(BaseModel):
    """Request to submit a lead from the landing page."""

    first_name: str
    last_name: str | None = None
    phone_number: str
    email: EmailStr | None = None
    company_name: str | None = None
    notes: str | None = None
    source: str | None = "landing_page"
    trigger_call: bool = False
    trigger_text: bool = False

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        """Validate first name is not empty."""
        if not v or not v.strip():
            msg = "First name is required"
            raise ValueError(msg)
        return v.strip()


class LeadSubmitResponse(BaseModel):
    """Response from lead submission."""

    success: bool
    message: str
    contact_id: int | None = None
    demo_initiated: bool = False


async def check_rate_limits(
    db: DB,
    client_ip: str,
    phone_number: str,
    request_type: str,
) -> None:
    """Check rate limits for demo requests.

    Args:
        db: Database session
        client_ip: Client IP address
        phone_number: Phone number being requested
        request_type: Type of request (call or text)

    Raises:
        HTTPException: If rate limit exceeded
    """
    now = datetime.now(UTC)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)

    # Check IP rate limit: 3 requests per hour
    ip_count_result = await db.execute(
        select(func.count()).where(
            DemoRequest.client_ip == client_ip,
            DemoRequest.created_at >= hour_ago,
        )
    )
    ip_count = ip_count_result.scalar() or 0

    if ip_count >= settings.demo_ip_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )

    # Check phone rate limit: 2 requests per day
    phone_count_result = await db.execute(
        select(func.count()).where(
            DemoRequest.phone_number == phone_number,
            DemoRequest.created_at >= day_ago,
        )
    )
    phone_count = phone_count_result.scalar() or 0

    if phone_count >= settings.demo_phone_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This phone number has reached its daily limit. Please try again tomorrow.",
        )




@router.post("/call", response_model=DemoResponse)
async def trigger_demo_call(
    demo_request: DemoCallRequest,
    request: Request,
    db: DB,
) -> DemoResponse:
    """Trigger a demo AI call to the provided phone number.

    This is a public endpoint with rate limiting.
    """
    # Validate configuration
    if not settings.demo_workspace_id or not settings.demo_agent_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo service not configured",
        )

    if not settings.telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not available",
        )

    client_ip = get_client_ip(request, settings.trusted_proxies)

    # Check rate limits
    await check_rate_limits(db, client_ip, demo_request.phone_number, "call")

    # Record the request
    demo_record = DemoRequest(
        phone_number=demo_request.phone_number,
        request_type="call",
        client_ip=client_ip,
    )
    db.add(demo_record)
    await db.flush()

    # Initiate the call
    voice_service = TelnyxVoiceService(settings.telnyx_api_key)
    try:
        # Build webhook URL for call events
        api_base = settings.api_base_url or "https://example.com"
        webhook_url = f"{api_base}/webhooks/telnyx/voice"

        # Connection ID is optional - service auto-discovers if not provided
        connection_id = settings.telnyx_connection_id if settings.telnyx_connection_id else None

        await voice_service.initiate_call(
            to_number=demo_request.phone_number,
            from_number=settings.demo_from_phone_number,
            connection_id=connection_id,
            webhook_url=webhook_url,
            db=db,
            workspace_id=uuid.UUID(settings.demo_workspace_id),
            contact_phone=demo_request.phone_number,
            agent_id=uuid.UUID(settings.demo_agent_id),
        )

        demo_record.status = "initiated"
        await db.commit()

        return DemoResponse(
            success=True,
            message="Call initiated! You should receive a call within 10 seconds.",
        )
    except Exception as e:
        demo_record.status = "failed"
        demo_record.error_message = str(e)[:500]
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate call. Please try again.",
        ) from e
    finally:
        await voice_service.close()


@router.post("/text", response_model=DemoResponse)
async def trigger_demo_text(
    demo_request: DemoTextRequest,
    request: Request,
    db: DB,
) -> DemoResponse:
    """Trigger a demo AI text to the provided phone number.

    This is a public endpoint with rate limiting.
    """
    # Validate configuration
    if not settings.demo_workspace_id or not settings.demo_agent_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo service not configured",
        )

    if not settings.telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service not available",
        )

    client_ip = get_client_ip(request, settings.trusted_proxies)

    # Check rate limits
    await check_rate_limits(db, client_ip, demo_request.phone_number, "text")

    # Record the request
    demo_record = DemoRequest(
        phone_number=demo_request.phone_number,
        request_type="text",
        client_ip=client_ip,
    )
    db.add(demo_record)
    await db.flush()

    # Send initial text message
    sms_service = TelnyxSMSService(settings.telnyx_api_key)
    try:
        await sms_service.send_message(
            to_number=demo_request.phone_number,
            from_number=settings.demo_from_phone_number,
            body=(
                "Hey! This is Jess from Prestige. I help businesses automate "
                "their customer conversations with AI. Want to see what I can do? "
                "Reply with anything and let's chat!"
            ),
            db=db,
            workspace_id=uuid.UUID(settings.demo_workspace_id),
            agent_id=uuid.UUID(settings.demo_agent_id),
        )

        demo_record.status = "initiated"
        await db.commit()

        return DemoResponse(
            success=True,
            message="Text sent! Check your phone for a message from Jess.",
        )
    except Exception as e:
        demo_record.status = "failed"
        demo_record.error_message = str(e)[:500]
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send text. Please try again.",
        ) from e
    finally:
        await sms_service.close()


def _update_existing_contact(contact: Contact, lead_request: LeadSubmitRequest) -> None:
    """Update existing contact with new info from lead request."""
    contact.first_name = lead_request.first_name or contact.first_name
    contact.last_name = lead_request.last_name or contact.last_name
    contact.email = lead_request.email or contact.email
    contact.company_name = lead_request.company_name or contact.company_name
    if lead_request.notes:
        existing_notes = contact.notes or ""
        contact.notes = f"{existing_notes}\n---\n{lead_request.notes}".strip()


async def _trigger_demo_call(lead_request: LeadSubmitRequest, db: DB) -> bool:
    """Trigger a demo call. Returns True if successful."""
    try:
        voice_service = TelnyxVoiceService(settings.telnyx_api_key)
        api_base = settings.api_base_url or "https://example.com"
        await voice_service.initiate_call(
            to_number=lead_request.phone_number,
            from_number=settings.demo_from_phone_number,
            connection_id=settings.telnyx_connection_id or None,
            webhook_url=f"{api_base}/webhooks/telnyx/voice",
            db=db,
            workspace_id=uuid.UUID(settings.demo_workspace_id),
            contact_phone=lead_request.phone_number,
            agent_id=uuid.UUID(settings.demo_agent_id),
        )
        await voice_service.close()
        return True
    except Exception:
        return False


async def _trigger_demo_text(lead_request: LeadSubmitRequest, db: DB) -> bool:
    """Trigger a demo text. Returns True if successful."""
    try:
        sms_service = TelnyxSMSService(settings.telnyx_api_key)
        await sms_service.send_message(
            to_number=lead_request.phone_number,
            from_number=settings.demo_from_phone_number,
            body=(
                f"Hey {lead_request.first_name}! This is Jess from Prestige. "
                "Thanks for your interest! I help businesses automate their "
                "customer conversations with AI. Reply with anything and let's chat!"
            ),
            db=db,
            workspace_id=uuid.UUID(settings.demo_workspace_id),
            agent_id=uuid.UUID(settings.demo_agent_id),
        )
        await sms_service.close()
        return True
    except Exception:
        return False


@router.post("/leads", response_model=LeadSubmitResponse)
async def submit_lead(
    lead_request: LeadSubmitRequest,
    request: Request,
    db: DB,
) -> LeadSubmitResponse:
    """Submit a lead from the landing page.

    Creates a contact in the demo workspace. Optionally triggers a demo call or text.
    This is a public endpoint with rate limiting.
    """
    if not settings.demo_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lead submission not configured",
        )

    client_ip = get_client_ip(request, settings.trusted_proxies)
    await check_rate_limits(db, client_ip, lead_request.phone_number, "lead")

    # Check if contact already exists in demo workspace
    workspace_id = uuid.UUID(settings.demo_workspace_id)
    result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.phone_number == lead_request.phone_number,
        )
    )
    existing_contact = result.scalar_one_or_none()

    if existing_contact:
        _update_existing_contact(existing_contact, lead_request)
        contact = existing_contact
    else:
        contact = Contact(
            workspace_id=workspace_id,
            first_name=lead_request.first_name,
            last_name=lead_request.last_name,
            phone_number=lead_request.phone_number,
            email=lead_request.email,
            company_name=lead_request.company_name,
            notes=lead_request.notes,
            source=lead_request.source or "landing_page",
            status="new",
        )
        db.add(contact)

    demo_record = DemoRequest(
        phone_number=lead_request.phone_number,
        request_type="lead",
        client_ip=client_ip,
    )
    db.add(demo_record)
    await db.flush()

    # Optionally trigger demo call or text
    demo_initiated = False
    can_trigger = settings.demo_agent_id and settings.telnyx_api_key
    if can_trigger and lead_request.trigger_call:
        demo_initiated = await _trigger_demo_call(lead_request, db)
    elif can_trigger and lead_request.trigger_text:
        demo_initiated = await _trigger_demo_text(lead_request, db)

    demo_record.status = "initiated"
    await db.commit()

    message = "Thanks for your interest! We'll be in touch soon."
    if demo_initiated and lead_request.trigger_call:
        message = "Thanks! You should receive a call within 10 seconds."
    elif demo_initiated:
        message = "Thanks! Check your phone for a text from Jess."

    return LeadSubmitResponse(
        success=True,
        message=message,
        contact_id=contact.id,
        demo_initiated=demo_initiated,
    )
