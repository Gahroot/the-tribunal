"""Outbound compliance checks for SMS and campaign sends."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.services.rate_limiting.opt_out_manager import OptOutManager

logger = structlog.get_logger()

# Compliance reasons that withhold one recipient until the operator changes
# something about that contact (as opposed to timing/capacity reasons such as
# ``quiet_hours`` or ``campaign_send_cap_reached``, which only defer a send).
RECIPIENT_EXCLUSION_REASONS: frozenset[str] = frozenset(
    {
        "global_opt_out",
        "missing_sms_consent",
        "missing_phone_number",
        "duplicate_campaign_contact",
        "contact_send_cap_reached",
    }
)


@dataclass(slots=True, frozen=True)
class OutboundComplianceRequest:
    """Input for outbound compliance evaluation."""

    workspace_id: uuid.UUID
    campaign: Campaign
    campaign_contact: CampaignContact | None
    contact: Contact
    channel: str
    action_type: str
    now: datetime
    require_sms_consent: bool = True
    # Campaign-wide gates (quiet hours, campaign send cap) defer sends rather
    # than exclude a recipient. Launch previews report them once per campaign;
    # real sends always keep them on.
    include_campaign_gates: bool = True
    # Optional pre-fetched workspace opt-out set (from
    # ``OptOutManager.opted_out_numbers``) so batch previews avoid one query
    # per recipient. ``None`` means "query the opt-out list".
    known_opted_out_numbers: frozenset[str] | None = None


@dataclass(slots=True, frozen=True)
class OutboundComplianceResult:
    """Result of outbound compliance evaluation."""

    allowed: bool
    reason: str | None = None
    details: dict[str, object] = field(default_factory=dict)
    next_allowed_at: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize the result for storage."""
        payload: dict[str, object] = {
            "allowed": self.allowed,
            "reason": self.reason,
            "details": self.details,
        }
        if self.next_allowed_at is not None:
            payload["next_allowed_at"] = self.next_allowed_at.isoformat()
        return payload


class OutboundComplianceService:
    """Evaluate outbound campaign and SMS compliance controls."""

    OPTED_IN = "opted_in"

    def __init__(self, opt_out_manager: OptOutManager | None = None) -> None:
        self.opt_out_manager = opt_out_manager or OptOutManager()
        self.logger = logger.bind(component="outbound_compliance")

    async def _phone_block_reason(
        self,
        request: OutboundComplianceRequest,
        db: AsyncSession,
    ) -> str | None:
        """Block phoneless contacts (e.g. email-only leads) and opted-out numbers."""
        phone_number = request.contact.phone_number
        if not phone_number:
            return "missing_phone_number"
        if request.known_opted_out_numbers is not None:
            is_opted_out = phone_number in request.known_opted_out_numbers
        else:
            is_opted_out = await self.opt_out_manager.check_opt_out(
                request.workspace_id, phone_number, db
            )
        return "global_opt_out" if is_opted_out else None

    async def evaluate(  # noqa: PLR0911
        self,
        request: OutboundComplianceRequest,
        db: AsyncSession,
    ) -> OutboundComplianceResult:
        """Evaluate all compliance gates for a proposed outbound send."""
        phone_block = await self._phone_block_reason(request, db)
        if phone_block is not None:
            return self._blocked(phone_block, request)

        if request.channel == "sms" and request.require_sms_consent:
            consent_status = request.contact.sms_consent_status or "unknown"
            if consent_status != self.OPTED_IN:
                return self._blocked(
                    "missing_sms_consent",
                    request,
                    {"sms_consent_status": consent_status},
                )

        if request.include_campaign_gates:
            quiet_hours_result = self._evaluate_quiet_hours(request)
            if not quiet_hours_result.allowed:
                return quiet_hours_result

            cap_details = self.campaign_send_cap_details(request.campaign)
            if cap_details is not None:
                return self._blocked("campaign_send_cap_reached", request, cap_details)

        if request.campaign_contact is not None:
            if request.campaign_contact.messages_sent >= request.campaign.max_messages_per_contact:
                return self._blocked(
                    "contact_send_cap_reached",
                    request,
                    {
                        "messages_sent": request.campaign_contact.messages_sent,
                        "max_messages_per_contact": request.campaign.max_messages_per_contact,
                    },
                )

            if request.action_type == "campaign_initial_sms":
                duplicate_exists = await self._has_initial_duplicate(request, db)
                if duplicate_exists:
                    return self._blocked("duplicate_campaign_contact", request)

        return OutboundComplianceResult(
            allowed=True,
            details={
                "action_type": request.action_type,
                "channel": request.channel,
                "campaign_id": str(request.campaign.id),
                "contact_id": request.contact.id,
            },
        )

    def apply_suppression(
        self,
        campaign_contact: CampaignContact,
        result: OutboundComplianceResult,
        now: datetime | None = None,
    ) -> None:
        """Persist suppression metadata on a campaign contact."""
        checked_at = now or datetime.now(UTC)
        campaign_contact.compliance_checked_at = checked_at
        campaign_contact.last_compliance_result = result.as_dict()

        if result.allowed:
            # A contact that was previously deferred/excluded (e.g. quiet hours,
            # missing consent later recorded) must not keep a stale reason.
            campaign_contact.suppressed_reason = None
            campaign_contact.suppressed_at = None
            return

        campaign_contact.suppressed_reason = result.reason
        campaign_contact.suppressed_at = checked_at
        if result.reason == "global_opt_out":
            campaign_contact.status = CampaignContactStatus.OPTED_OUT
            campaign_contact.opted_out = True
            campaign_contact.opted_out_at = checked_at

    async def _has_initial_duplicate(
        self,
        request: OutboundComplianceRequest,
        db: AsyncSession,
    ) -> bool:
        if request.campaign_contact is None:
            return False

        duplicate_query = select(
            exists().where(
                and_(
                    CampaignContact.campaign_id == request.campaign.id,
                    CampaignContact.contact_id == request.contact.id,
                    CampaignContact.id != request.campaign_contact.id,
                    CampaignContact.status.in_(
                        [
                            CampaignContactStatus.SENT,
                            CampaignContactStatus.DELIVERED,
                            CampaignContactStatus.REPLIED,
                            CampaignContactStatus.QUALIFIED,
                            CampaignContactStatus.COMPLETED,
                        ]
                    )
                    | (CampaignContact.conversation_id.is_not(None))
                    | (CampaignContact.first_sent_at.is_not(None)),
                )
            )
        )
        duplicate_result = await db.execute(duplicate_query)
        return bool(duplicate_result.scalar())

    @staticmethod
    def campaign_send_cap_details(campaign: Campaign) -> dict[str, object] | None:
        """Return cap details when the campaign has reached its total send cap."""
        if (
            campaign.max_messages_per_campaign is not None
            and campaign.messages_sent >= campaign.max_messages_per_campaign
        ):
            return {
                "messages_sent": campaign.messages_sent,
                "max_messages_per_campaign": campaign.max_messages_per_campaign,
            }
        return None

    def quiet_hours_details(self, campaign: Campaign, now: datetime) -> dict[str, object] | None:
        """Return quiet-hours details when ``now`` is inside the campaign's quiet hours."""
        start = campaign.quiet_hours_start
        end = campaign.quiet_hours_end
        if start is None or end is None:
            return None

        timezone_name = campaign.quiet_hours_timezone or campaign.timezone or "UTC"
        try:
            local_now = now.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            self.logger.warning(
                "invalid_quiet_hours_timezone",
                timezone=timezone_name,
                campaign_id=str(campaign.id),
            )
            local_now = now.astimezone(ZoneInfo("UTC"))
            timezone_name = "UTC"

        local_time = local_now.time()
        if start <= end:
            in_quiet_hours = start <= local_time < end
        else:
            in_quiet_hours = local_time >= start or local_time < end

        if not in_quiet_hours:
            return None

        return {
            "quiet_hours_start": start.isoformat(),
            "quiet_hours_end": end.isoformat(),
            "timezone": timezone_name,
            "local_time": local_time.isoformat(),
        }

    def _evaluate_quiet_hours(self, request: OutboundComplianceRequest) -> OutboundComplianceResult:
        details = self.quiet_hours_details(request.campaign, request.now)
        if details is None:
            return OutboundComplianceResult(allowed=True)
        return self._blocked("quiet_hours", request, details)

    def _blocked(
        self,
        reason: str,
        request: OutboundComplianceRequest,
        details: dict[str, object] | None = None,
    ) -> OutboundComplianceResult:
        result_details: dict[str, object] = {
            "action_type": request.action_type,
            "channel": request.channel,
            "campaign_id": str(request.campaign.id),
            "contact_id": request.contact.id,
        }
        if details:
            result_details.update(details)
        return OutboundComplianceResult(allowed=False, reason=reason, details=result_details)
