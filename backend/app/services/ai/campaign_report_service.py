"""Campaign post-mortem intelligence service.

Analyzes completed campaign results and generates structured
intelligence reports using GPT-4o.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI
from sqlalchemy import Integer as SAInteger
from sqlalchemy import case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import extract

from app.core.config import settings
from app.models.call_outcome import CallOutcome
from app.models.campaign import Campaign, CampaignContact, CampaignType
from app.models.campaign_report import CampaignReport

logger = structlog.get_logger()


class CampaignReportService:
    """Generates AI-powered post-mortem reports for completed campaigns."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def generate_report(
        self, db: AsyncSession, campaign_id: uuid.UUID
    ) -> CampaignReport:
        """Generate a post-mortem intelligence report for a campaign."""
        log = logger.bind(campaign_id=str(campaign_id))

        # Load campaign
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        # Check for existing report
        existing = await db.execute(
            select(CampaignReport).where(CampaignReport.campaign_id == campaign_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Report already exists for campaign {campaign_id}")

        # Create report in "generating" status
        report = CampaignReport(
            campaign_id=campaign.id,
            workspace_id=campaign.workspace_id,
            status="generating",
        )
        db.add(report)
        await db.flush()

        try:
            # Gather all data
            data = await self._gather_campaign_data(db, campaign)
            log.info("Campaign data gathered", contact_count=data.get("total_contacts", 0))

            # Analyze with LLM
            analysis = await self._analyze_with_llm(data)

            # Populate report
            report.metrics_snapshot = data.get("metrics", {})
            report.executive_summary = analysis.get("executive_summary", "")
            report.key_findings = analysis.get("key_findings", [])
            report.what_worked = analysis.get("what_worked", [])
            report.what_didnt_work = analysis.get("what_didnt_work", [])
            report.recommendations = analysis.get("recommendations", [])
            report.segment_analysis = analysis.get("segment_analysis", [])
            report.timing_analysis = analysis.get("timing_analysis", {})
            report.prompt_performance = data.get("prompt_performance", [])
            report.status = "completed"
            report.generated_at = datetime.now(UTC)

            await db.flush()
            log.info("Campaign report generated successfully")

        except Exception:
            log.exception("Failed to generate campaign report")
            report.status = "failed"
            report.error_message = "Report generation failed. Please try again."
            await db.flush()

        return report

    async def _gather_campaign_data(
        self, db: AsyncSession, campaign: Campaign
    ) -> dict[str, Any]:
        """Collect all data needed for analysis."""
        data: dict[str, Any] = {
            "campaign_name": campaign.name,
            "campaign_type": campaign.campaign_type,
            "total_contacts": campaign.total_contacts,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        }

        # Frozen metrics
        data["metrics"] = {
            "total_contacts": campaign.total_contacts,
            "messages_sent": campaign.messages_sent,
            "messages_delivered": campaign.messages_delivered,
            "messages_failed": campaign.messages_failed,
            "replies_received": campaign.replies_received,
            "contacts_qualified": campaign.contacts_qualified,
            "contacts_opted_out": campaign.contacts_opted_out,
            "appointments_booked": campaign.appointments_booked,
            "calls_attempted": campaign.calls_attempted,
            "calls_answered": campaign.calls_answered,
            "calls_no_answer": campaign.calls_no_answer,
            "calls_busy": campaign.calls_busy,
            "calls_voicemail": campaign.calls_voicemail,
            "sms_fallbacks_sent": campaign.sms_fallbacks_sent,
        }

        # Contact status distribution
        status_dist = await self._gather_status_distribution(db, campaign)
        data["status_distribution"] = status_dist

        # Timing analysis
        timing = await self._gather_timing_data(db, campaign)
        data["timing"] = timing

        # Type-specific data
        if campaign.campaign_type == CampaignType.VOICE_SMS_FALLBACK.value:
            voice_data = await self._gather_voice_data(db, campaign)
            data["voice"] = voice_data
        else:
            sms_data = await self._gather_sms_data(db, campaign)
            data["sms"] = sms_data

        return data

    async def _gather_status_distribution(
        self, db: AsyncSession, campaign: Campaign
    ) -> list[dict[str, Any]]:
        """Get contact status distribution."""
        result = await db.execute(
            select(
                CampaignContact.status,
                func.count(CampaignContact.id).label("count"),
            )
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(CampaignContact.status)
        )
        return [
            {"status": row.status, "count": row.count}
            for row in result.all()
        ]

    async def _gather_voice_data(
        self, db: AsyncSession, campaign: Campaign
    ) -> dict[str, Any]:
        """Gather voice-specific campaign data."""
        # Call outcome distribution
        outcome_result = await db.execute(
            select(
                CallOutcome.outcome_type,
                func.count(CallOutcome.id).label("count"),
            )
            .join(
                CampaignContact,
                CampaignContact.call_message_id == CallOutcome.message_id,
            )
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(CallOutcome.outcome_type)
        )
        outcome_dist = [
            {"outcome": row.outcome_type, "count": row.count}
            for row in outcome_result.all()
        ]

        # Average call duration for answered calls
        duration_result = await db.execute(
            select(
                func.avg(CampaignContact.call_duration_seconds).label("avg_duration"),
                func.max(CampaignContact.call_duration_seconds).label("max_duration"),
                func.min(CampaignContact.call_duration_seconds).label("min_duration"),
            )
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.call_duration_seconds.is_not(None),
                CampaignContact.call_duration_seconds > 0,
            )
        )
        duration_row = duration_result.one_or_none()
        duration_stats = {}
        if duration_row:
            duration_stats = {
                "avg_seconds": float(duration_row.avg_duration or 0),
                "max_seconds": int(duration_row.max_duration or 0),
                "min_seconds": int(duration_row.min_duration or 0),
            }

        # Prompt version performance
        prompt_perf = await self._gather_prompt_performance(db, campaign)

        return {
            "outcome_distribution": outcome_dist,
            "duration_stats": duration_stats,
            "prompt_performance": prompt_perf,
        }

    async def _gather_prompt_performance(
        self, db: AsyncSession, campaign: Campaign
    ) -> list[dict[str, Any]]:
        """Get performance breakdown by prompt version."""
        result = await db.execute(
            select(
                CallOutcome.prompt_version_id,
                func.count(CallOutcome.id).label("total_calls"),
                func.sum(
                    case(
                        (
                            CallOutcome.outcome_type.in_(["appointment_booked", "lead_qualified"]),
                            1,
                        ),
                        else_=0,
                    )
                ).label("successful"),
            )
            .join(
                CampaignContact,
                CampaignContact.call_message_id == CallOutcome.message_id,
            )
            .where(
                CampaignContact.campaign_id == campaign.id,
                CallOutcome.prompt_version_id.is_not(None),
            )
            .group_by(CallOutcome.prompt_version_id)
        )
        rows = result.all()
        return [
            {
                "version_id": str(row.prompt_version_id),
                "calls": row.total_calls,
                "successful": int(row.successful or 0),
                "success_rate": round(
                    (int(row.successful or 0) / row.total_calls * 100)
                    if row.total_calls > 0
                    else 0,
                    1,
                ),
            }
            for row in rows
        ]

    async def _gather_sms_data(
        self, db: AsyncSession, campaign: Campaign
    ) -> dict[str, Any]:
        """Gather SMS-specific campaign data."""
        # Reply rate by follow-up count
        followup_result = await db.execute(
            select(
                CampaignContact.follow_ups_sent,
                func.count(CampaignContact.id).label("total"),
                func.sum(
                    case(
                        (CampaignContact.messages_received > 0, 1),
                        else_=0,
                    )
                ).label("replied"),
            )
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(CampaignContact.follow_ups_sent)
            .order_by(CampaignContact.follow_ups_sent)
        )
        followup_stats = [
            {
                "follow_ups_sent": row.follow_ups_sent,
                "total": row.total,
                "replied": int(row.replied or 0),
            }
            for row in followup_result.all()
        ]

        # Opt-out timing (how many messages before opt-out)
        optout_result = await db.execute(
            select(
                func.avg(CampaignContact.messages_sent).label("avg_messages_before_optout"),
            )
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.opted_out.is_(True),
            )
        )
        optout_row = optout_result.one_or_none()

        return {
            "followup_conversion": followup_stats,
            "avg_messages_before_optout": float(optout_row.avg_messages_before_optout or 0)
            if optout_row
            else 0,
        }

    async def _gather_timing_data(
        self, db: AsyncSession, campaign: Campaign
    ) -> dict[str, Any]:
        """Gather hourly/daily activity distributions."""
        hour_col = cast(extract("hour", CampaignContact.first_sent_at), SAInteger).label("hour")
        # Hourly distribution from first_sent_at
        hourly_result = await db.execute(
            select(
                hour_col,
                func.count(CampaignContact.id).label("sent"),
                func.sum(
                    case(
                        (CampaignContact.is_qualified.is_(True), 1),
                        else_=0,
                    )
                ).label("qualified"),
            )
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.first_sent_at.is_not(None),
            )
            .group_by(hour_col)
            .order_by(hour_col)
        )
        hourly = [
            {"hour": row.hour, "sent": row.sent, "qualified": int(row.qualified or 0)}
            for row in hourly_result.all()
        ]

        dow_col = cast(extract("dow", CampaignContact.first_sent_at), SAInteger).label("dow")
        # Day-of-week distribution
        dow_result = await db.execute(
            select(
                dow_col,
                func.count(CampaignContact.id).label("sent"),
                func.sum(
                    case(
                        (CampaignContact.is_qualified.is_(True), 1),
                        else_=0,
                    )
                ).label("qualified"),
            )
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.first_sent_at.is_not(None),
            )
            .group_by(dow_col)
            .order_by(dow_col)
        )
        daily = [
            {"day_of_week": row.dow, "sent": row.sent, "qualified": int(row.qualified or 0)}
            for row in dow_result.all()
        ]

        return {"hourly": hourly, "daily": daily}

    async def _analyze_with_llm(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send gathered data to GPT-4o for analysis."""
        client = self._get_client()

        system_prompt = (
            "You are an expert campaign analyst for AI-powered sales systems. "
            "You analyze completed campaign data and produce actionable intelligence reports. "
            "Be specific, data-driven, and actionable in your analysis."
        )

        campaign_json = json.dumps(data, indent=2, default=str)
        user_prompt = (
            "Analyze this completed campaign and produce a "
            "structured intelligence report.\n\n"
            f"CAMPAIGN DATA:\n{campaign_json}\n\n"
            "Return a JSON object with exactly these fields:\n"
            '- "executive_summary": 2-3 paragraph overview of '
            "campaign performance and strategic implications\n"
            '- "key_findings": Array of {{title, description, '
            'metric, sentiment}} (positive/negative/neutral)\n'
            '- "what_worked": Array of '
            "{{title, description, evidence}}\n"
            '- "what_didnt_work": Array of '
            "{{title, description, evidence}}\n"
            '- "recommendations": Array of '
            "{{title, description, priority, action_type}} "
            "priority=high/medium/low, action_type="
            "prompt_change/timing_adjustment/"
            "audience_refinement/follow_up_strategy/general\n"
            '- "segment_analysis": Array of '
            "{{segment_name, size, conversion_rate, insights}}\n"
            '- "timing_analysis": Object with '
            "{{best_hours, worst_hours, best_days, worst_days, "
            "recommendation}}\n\n"
            "Be specific with numbers and percentages. "
            "Reference actual data from the campaign."
        )

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        text = response.choices[0].message.content or "{}"
        return json.loads(text)  # type: ignore[no-any-return]
