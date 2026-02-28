"""Public lead form endpoint for external website submissions."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import DB
from app.core.config import settings
from app.core.origin_validation import validate_origin
from app.core.utils import get_client_ip
from app.models.campaign import CampaignContact
from app.models.contact import Contact
from app.models.demo_request import DemoRequest
from app.models.lead_source import LeadSource
from app.schemas.lead_source import LeadSubmitRequest, LeadSubmitResponse
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.telephony.telnyx_voice import TelnyxVoiceService

logger = structlog.get_logger()

router = APIRouter()


async def _check_lead_form_rate_limit(db: DB, client_ip: str) -> None:
    """Check IP rate limit for lead form submissions."""
    hour_ago = datetime.now(UTC) - timedelta(hours=1)
    result = await db.execute(
        select(func.count()).where(
            DemoRequest.client_ip == client_ip,
            DemoRequest.request_type == "lead_form",
            DemoRequest.created_at >= hour_ago,
        )
    )
    count = result.scalar() or 0
    if count >= settings.lead_form_ip_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )


async def _action_auto_text(
    lead_source: LeadSource, contact: Contact, db: DB
) -> None:
    """Send an automatic text message to the lead."""
    config = lead_source.action_config or {}
    from_number = config.get("from_phone_number", settings.demo_from_phone_number)
    template = config.get("message_template") or (
        f"Hi {contact.first_name}! Thanks for your interest. "
        "We'll be in touch shortly."
    )
    if not settings.telnyx_api_key or not from_number:
        logger.warning("auto_text_skipped", reason="telnyx not configured")
        return
    sms_service = TelnyxSMSService(settings.telnyx_api_key)
    try:
        agent_id_str = config.get("agent_id")
        await sms_service.send_message(
            to_number=contact.phone_number,
            from_number=from_number,
            body=template,
            db=db,
            workspace_id=lead_source.workspace_id,
            agent_id=uuid.UUID(agent_id_str) if agent_id_str else None,
        )
    except Exception:
        logger.exception("auto_text_failed", contact_id=contact.id)
    finally:
        await sms_service.close()


async def _action_auto_call(
    lead_source: LeadSource, contact: Contact, db: DB
) -> None:
    """Initiate an automatic call to the lead."""
    config = lead_source.action_config or {}
    from_number = config.get("from_phone_number", settings.demo_from_phone_number)
    if not settings.telnyx_api_key or not from_number:
        logger.warning("auto_call_skipped", reason="telnyx not configured")
        return
    voice_service = TelnyxVoiceService(settings.telnyx_api_key)
    try:
        api_base = settings.api_base_url or "https://example.com"
        agent_id_str = config.get("agent_id")
        await voice_service.initiate_call(
            to_number=contact.phone_number,
            from_number=from_number,
            connection_id=settings.telnyx_connection_id or None,
            webhook_url=f"{api_base}/webhooks/telnyx/voice",
            db=db,
            workspace_id=lead_source.workspace_id,
            contact_phone=contact.phone_number,
            agent_id=uuid.UUID(agent_id_str) if agent_id_str else None,
        )
    except Exception:
        logger.exception("auto_call_failed", contact_id=contact.id)
    finally:
        await voice_service.close()


async def _action_enroll_campaign(
    lead_source: LeadSource, contact: Contact, db: DB
) -> None:
    """Enroll the lead in a campaign."""
    config = lead_source.action_config or {}
    campaign_id_str = config.get("campaign_id")
    if not campaign_id_str:
        logger.warning("enroll_campaign_skipped", reason="no campaign_id")
        return
    try:
        campaign_id = uuid.UUID(campaign_id_str)
        existing = await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign_id,
                CampaignContact.contact_id == contact.id,
            )
        )
        if not existing.scalar_one_or_none():
            cc = CampaignContact(
                campaign_id=campaign_id,
                contact_id=contact.id,
                status="pending",
            )
            db.add(cc)
    except Exception:
        logger.exception("enroll_campaign_failed", contact_id=contact.id)


_ACTION_HANDLERS = {
    "auto_text": _action_auto_text,
    "auto_call": _action_auto_call,
    "enroll_campaign": _action_enroll_campaign,
}


async def _execute_action(
    lead_source: LeadSource,
    contact: Contact,
    db: DB,
) -> None:
    """Execute the post-capture action configured on the lead source."""
    handler = _ACTION_HANDLERS.get(lead_source.action)
    if handler:
        await handler(lead_source, contact, db)


@router.options("/{public_key}")
async def lead_form_preflight(
    public_key: str,
    request: Request,
    db: DB,
) -> Response:
    """Handle CORS preflight for lead form submissions."""
    result = await db.execute(
        select(LeadSource).where(
            LeadSource.public_key == public_key,
            LeadSource.enabled.is_(True),
        )
    )
    lead_source = result.scalar_one_or_none()

    origin = request.headers.get("origin", "")
    if lead_source and validate_origin(request, lead_source.allowed_domains):
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "86400",
            },
        )
    return Response(status_code=403)


@router.post("/{public_key}", response_model=LeadSubmitResponse)
async def submit_lead(
    public_key: str,
    body: LeadSubmitRequest,
    request: Request,
    db: DB,
) -> Response:
    """Submit a lead from an external website form.

    Public endpoint secured by origin whitelist and rate limiting.
    """
    # Look up lead source
    result = await db.execute(
        select(LeadSource).where(LeadSource.public_key == public_key)
    )
    lead_source = result.scalar_one_or_none()

    if not lead_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead source not found")

    if not lead_source.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lead source is disabled")

    # Validate origin
    if not validate_origin(request, lead_source.allowed_domains):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed")

    # Rate limit
    client_ip = get_client_ip(request, settings.trusted_proxies)
    await _check_lead_form_rate_limit(db, client_ip)

    # Record rate limit entry
    demo_record = DemoRequest(
        phone_number=body.phone_number,
        request_type="lead_form",
        client_ip=client_ip,
    )
    db.add(demo_record)

    # Deduplicate: find existing contact by phone in workspace
    existing_result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == lead_source.workspace_id,
            Contact.phone_number == body.phone_number,
        )
    )
    existing_contact = existing_result.scalar_one_or_none()

    if existing_contact:
        # Update existing contact with new info
        existing_contact.first_name = body.first_name or existing_contact.first_name
        existing_contact.last_name = body.last_name or existing_contact.last_name
        existing_contact.email = body.email or existing_contact.email
        existing_contact.company_name = body.company_name or existing_contact.company_name
        if body.notes:
            existing_notes = existing_contact.notes or ""
            existing_contact.notes = f"{existing_notes}\n---\n{body.notes}".strip()
        if body.source_detail:
            existing_notes = existing_contact.notes or ""
            existing_contact.notes = f"{existing_notes}\n[source: {body.source_detail}]".strip()
        contact = existing_contact
    else:
        notes = body.notes or ""
        if body.source_detail:
            source_tag = f"[source: {body.source_detail}]"
            notes = f"{notes}\n{source_tag}".strip() if notes else source_tag
        contact = Contact(
            workspace_id=lead_source.workspace_id,
            first_name=body.first_name,
            last_name=body.last_name,
            phone_number=body.phone_number,
            email=body.email,
            company_name=body.company_name,
            notes=notes or None,
            source="lead_form",
            status="new",
        )
        db.add(contact)

    await db.flush()

    # Execute post-capture action
    await _execute_action(lead_source, contact, db)

    demo_record.status = "initiated"
    await db.commit()

    # Build response with CORS header
    origin = request.headers.get("origin", "")
    response_data = LeadSubmitResponse(
        success=True,
        message="Thank you! Your information has been received.",
    )

    return Response(
        content=response_data.model_dump_json(),
        media_type="application/json",
        headers={"Access-Control-Allow-Origin": origin},
    )
