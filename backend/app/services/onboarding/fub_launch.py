"""Retry-safe guided FUB launch. Never imports, syncs, or sends outreach here."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.services.campaigns.campaign_lifecycle import CampaignLifecycleError, start_campaign
from app.services.campaigns.recipient_eligibility import RecipientEligibilityService
from app.services.onboarding.exceptions import OnboardingValidationError
from app.services.onboarding.workspace_setup import (
    create_realtor_campaign,
    enroll_campaign_contacts,
    get_realtor_agent,
    get_realtor_sms_phone_number,
)


@dataclass(frozen=True)
class FUBLaunchResult:
    campaign_id: uuid.UUID | None
    campaign_status: str | None
    launch_status: str
    message: str


async def _load_workspace_contacts(
    db: AsyncSession, workspace_id: uuid.UUID, contact_ids: list[int]
) -> list[Contact]:
    audience_ids = sorted(set(contact_ids))
    contacts: list[Contact] = []
    # Keep even large imports below the database driver's bind limit.
    for offset in range(0, len(audience_ids), 1000):
        contacts.extend(
            (
                await db.execute(
                    select(Contact).where(
                        Contact.workspace_id == workspace_id,
                        Contact.id.in_(audience_ids[offset : offset + 1000]),
                    )
                )
            )
            .scalars()
            .all()
        )
    if len(contacts) != len(audience_ids):
        raise OnboardingValidationError(
            "Imported contacts are missing from this workspace. Import again."
        )
    return contacts


async def launch_fub_campaign(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    contact_ids: list[int],
    campaign_name: str,
) -> FUBLaunchResult:
    """One onboarding campaign per workspace, including after a lost response.

    The workspace row lock serializes concurrent retries. Only draft campaigns
    may be started here: retries never restart completed campaigns, reset sent
    recipients, or append a new audience to an already-launched campaign.
    The caller must authorize membership before invoking this workflow.
    """
    await db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    campaign_id = uuid.uuid5(workspace_id, "onboarding-fub-launch")
    campaign = (
        await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    try:
        agent = await get_realtor_agent(db=db, workspace_id=workspace_id)
        phone = await get_realtor_sms_phone_number(db=db, workspace_id=workspace_id)
        if phone.imessage_enabled:
            if not (settings.mac_relay_base_url and settings.mac_relay_token):
                raise OnboardingValidationError(
                    "iMessage relay is not configured for campaign sending"
                )
        elif not settings.telnyx_api_key:
            raise OnboardingValidationError("Telnyx SMS is not configured for campaign sending")
        if campaign is None or campaign.status == CampaignStatus.DRAFT:
            contacts = await _load_workspace_contacts(db, workspace_id, contact_ids)
            if campaign is None:
                campaign = await create_realtor_campaign(
                    db=db,
                    workspace_id=workspace_id,
                    agent=agent,
                    phone_record=phone,
                    campaign_name=campaign_name,
                    now=lambda: datetime.now(UTC),
                    campaign_id=campaign_id,
                )
                existing_ids: set[int] = set()
            else:
                # A partial import may be corrected before a blocked draft starts.
                # Preserve existing recipients; add only newly imported contacts.
                existing_ids = set(
                    (
                        await db.execute(
                            select(CampaignContact.contact_id).where(
                                CampaignContact.campaign_id == campaign.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            new_contacts = [contact for contact in contacts if contact.id not in existing_ids]
            campaign.total_contacts = len(existing_ids) + enroll_campaign_contacts(
                db, campaign, new_contacts
            )
            await db.flush()
        if campaign.status == CampaignStatus.DRAFT:
            # Recovery can use the now-ready sender without recreating enrollment.
            campaign.from_phone_number = phone.phone_number
            campaign.agent_id = agent.id
            result = await start_campaign(db, campaign)
            message = result.message
            eligibility = result.eligibility
        else:
            eligibility = await RecipientEligibilityService().evaluate_campaign(db, campaign)
            message = (
                f"Existing campaign is {campaign.status}. No new sends were queued by this retry."
            )
        outcome = str(campaign.status)
        if (
            campaign.status == CampaignStatus.RUNNING
            and eligibility
            and eligibility.deferral_reason
        ):
            outcome = "deferred"
            message = f"Campaign running; sends deferred: {eligibility.deferral_label}."
        elif campaign.status not in (CampaignStatus.RUNNING, CampaignStatus.SCHEDULED):
            outcome = "blocked"
    except (OnboardingValidationError, CampaignLifecycleError) as exc:
        outcome = "blocked"
        message = str(exc)
    await db.commit()
    return FUBLaunchResult(
        campaign_id=campaign.id if campaign else None,
        campaign_status=str(campaign.status) if campaign else None,
        launch_status=outcome,
        message=message,
    )
