"""CRM tool executor — runs database-backed operations on behalf of the assistant."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.opportunity import Opportunity


class CRMToolExecutor:
    """Execute CRM tool calls on behalf of the assistant."""

    def __init__(self, db: AsyncSession, workspace_id: uuid.UUID, user_id: int) -> None:
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.log = structlog.get_logger(service="crm_tool_executor")

    async def execute(self, function_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call to the appropriate handler."""
        handlers: dict[str, Any] = {
            "search_contacts": self._search_contacts,
            "create_contact": self._create_contact,
            "list_campaigns": self._list_campaigns,
            "list_agents": self._list_agents,
            "send_sms": self._send_sms,
            "get_conversation": self._get_conversation,
            "list_recent_conversations": self._list_recent_conversations,
            "list_appointments": self._list_appointments,
            "get_dashboard_stats": self._get_dashboard_stats,
            "list_opportunities": self._list_opportunities,
        }
        handler = handlers.get(function_name)
        if not handler:
            return {"success": False, "error": f"Unknown function: {function_name}"}
        try:
            return await handler(arguments)  # type: ignore[no-any-return]
        except Exception:
            self.log.exception("tool_execution_failed", function_name=function_name)
            return {"success": False, "error": f"Failed to execute {function_name}"}

    # ── Handlers ────────────────────────────────────────────────────────

    async def _search_contacts(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args["query"]
        limit = min(args.get("limit", 10), 50)
        pattern = f"%{query}%"

        stmt = (
            select(Contact)
            .where(Contact.workspace_id == self.workspace_id)
            .where(
                (Contact.first_name.ilike(pattern))
                | (Contact.last_name.ilike(pattern))
                | (Contact.email.ilike(pattern))
                | (Contact.phone_number.ilike(pattern))
                | (Contact.company_name.ilike(pattern))
            )
            .order_by(Contact.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        contacts = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": c.id,
                    "first_name": c.first_name,
                    "last_name": c.last_name,
                    "phone": c.phone_number,
                    "email": c.email,
                    "status": c.status,
                    "company": c.company_name,
                }
                for c in contacts
            ],
            "count": len(contacts),
        }

    async def _create_contact(self, args: dict[str, Any]) -> dict[str, Any]:
        phone = args["phone"]
        # Check for duplicate
        existing = await self.db.execute(
            select(Contact).where(
                Contact.workspace_id == self.workspace_id,
                Contact.phone_number == phone,
            )
        )
        if existing.scalar_one_or_none():
            return {"success": False, "error": "Contact with this phone already exists"}

        contact = Contact(
            workspace_id=self.workspace_id,
            first_name=args["first_name"],
            last_name=args.get("last_name"),
            phone_number=phone,
            email=args.get("email"),
            notes=args.get("notes"),
        )
        self.db.add(contact)
        await self.db.flush()

        return {
            "success": True,
            "data": {
                "id": contact.id,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "phone": contact.phone_number,
            },
        }

    async def _list_campaigns(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = min(args.get("limit", 10), 50)
        stmt = (
            select(Campaign)
            .where(Campaign.workspace_id == self.workspace_id)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
        )
        if args.get("status"):
            stmt = stmt.where(Campaign.status == args["status"])

        result = await self.db.execute(stmt)
        campaigns = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "status": c.status,
                    "type": c.campaign_type,
                }
                for c in campaigns
            ],
            "count": len(campaigns),
        }

    async def _list_agents(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = min(args.get("limit", 10), 50)
        stmt = (
            select(Agent)
            .where(Agent.workspace_id == self.workspace_id)
            .order_by(Agent.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        agents = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "channel_mode": a.channel_mode,
                    "is_active": a.is_active,
                }
                for a in agents
            ],
            "count": len(agents),
        }

    async def _send_sms(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.core.config import settings
        from app.services.telephony.telnyx import TelnyxSMSService

        contact_id = args["contact_id"]
        body = args["body"]

        # Look up contact
        result = await self.db.execute(
            select(Contact).where(
                Contact.id == contact_id,
                Contact.workspace_id == self.workspace_id,
            )
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return {"success": False, "error": "Contact not found"}

        # Get a workspace phone number to send from
        from app.models.phone_number import PhoneNumber

        phone_result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == self.workspace_id
            ).limit(1)
        )
        phone = phone_result.scalar_one_or_none()
        if not phone:
            return {"success": False, "error": "No phone number available in workspace"}

        telnyx_key = settings.telnyx_api_key
        if not telnyx_key:
            return {"success": False, "error": "SMS not configured"}

        sms_service = TelnyxSMSService(telnyx_key)
        try:
            await sms_service.send_message(
                to_number=contact.phone_number,
                from_number=phone.phone_number,
                body=body,
                db=self.db,
                workspace_id=self.workspace_id,
            )
        finally:
            await sms_service.close()

        return {"success": True, "message": f"SMS sent to {contact.first_name}"}

    async def _get_conversation(self, args: dict[str, Any]) -> dict[str, Any]:
        contact_id = args["contact_id"]
        limit = min(args.get("limit", 20), 100)

        # Find conversation with this contact
        conv_result = await self.db.execute(
            select(Conversation)
            .where(
                Conversation.workspace_id == self.workspace_id,
                Conversation.contact_id == contact_id,
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(1)
        )
        conversation = conv_result.scalar_one_or_none()
        if not conversation:
            return {"success": True, "data": [], "count": 0}

        msg_result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = msg_result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "direction": m.direction,
                    "body": m.body,
                    "channel": m.channel,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in reversed(messages)
            ],
            "count": len(messages),
        }

    async def _list_recent_conversations(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = min(args.get("limit", 10), 50)
        stmt = (
            select(Conversation)
            .where(Conversation.workspace_id == self.workspace_id)
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        conversations = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": str(c.id),
                    "contact_phone": c.contact_phone,
                    "last_message": c.last_message_preview,
                    "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                    "unread_count": c.unread_count,
                }
                for c in conversations
            ],
            "count": len(conversations),
        }

    async def _list_appointments(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = min(args.get("limit", 10), 50)
        stmt = (
            select(Appointment)
            .where(
                Appointment.workspace_id == self.workspace_id,
                Appointment.scheduled_at >= datetime.now(UTC),
            )
            .order_by(Appointment.scheduled_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        appointments = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": a.id,
                    "contact_id": a.contact_id,
                    "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else None,
                    "duration_minutes": a.duration_minutes,
                    "status": a.status,
                    "notes": a.notes,
                }
                for a in appointments
            ],
            "count": len(appointments),
        }

    async def _get_dashboard_stats(self, _args: dict[str, Any]) -> dict[str, Any]:
        contacts_count = await self.db.scalar(
            select(func.count()).select_from(Contact).where(
                Contact.workspace_id == self.workspace_id
            )
        )
        campaigns_count = await self.db.scalar(
            select(func.count()).select_from(Campaign).where(
                Campaign.workspace_id == self.workspace_id
            )
        )
        conversations_count = await self.db.scalar(
            select(func.count()).select_from(Conversation).where(
                Conversation.workspace_id == self.workspace_id
            )
        )
        appointments_count = await self.db.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.workspace_id == self.workspace_id,
                Appointment.scheduled_at >= datetime.now(UTC),
            )
        )

        return {
            "success": True,
            "data": {
                "contacts": contacts_count or 0,
                "campaigns": campaigns_count or 0,
                "conversations": conversations_count or 0,
                "upcoming_appointments": appointments_count or 0,
            },
        }

    async def _list_opportunities(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = min(args.get("limit", 10), 50)
        stmt = (
            select(Opportunity)
            .where(Opportunity.workspace_id == self.workspace_id)
            .order_by(Opportunity.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        opportunities = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": str(o.id),
                    "name": o.name,
                    "status": o.status,
                    "amount": float(o.amount) if o.amount else None,
                    "probability": o.probability,
                }
                for o in opportunities
            ],
            "count": len(opportunities),
        }
