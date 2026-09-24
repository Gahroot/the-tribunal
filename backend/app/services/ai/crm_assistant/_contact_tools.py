"""Contact and dashboard CRM assistant tools."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func

from app.db.scope import select_workspace_owned
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services.ai.contact_timeline import (
    format_contact_timeline,
    read_contact_timeline,
    record_event,
)
from app.services.ai.crm_assistant._tool_context import CRMToolContext, ToolArguments, ToolHandler
from app.services.dashboard.today_queue_service import TodayQueueService


class ContactAssistantTools:
    """Read and mutate contacts for CRM assistant tool calls."""

    def __init__(self, context: CRMToolContext) -> None:
        self.context = context

    def handlers(self) -> dict[str, ToolHandler]:
        return {
            "search_contacts": self.search_contacts,
            "get_contact_timeline": self.get_contact_timeline,
            "record_contact_note": self.record_contact_note,
            "create_contact": self.create_contact,
            "get_dashboard_stats": self.get_dashboard_stats,
            "get_today_queue": self.get_today_queue,
        }

    async def search_contacts(self, args: ToolArguments) -> dict[str, object]:
        query = args["query"]
        limit = min(args.get("limit", 10), 50)
        pattern = f"%{query}%"

        stmt = (
            select_workspace_owned(Contact, self.context.workspace_id)
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
        result = await self.context.db.execute(stmt)
        contacts = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "id": contact.id,
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "phone": contact.phone_number,
                    "email": contact.email,
                    "status": contact.status,
                    "company": contact.company_name,
                }
                for contact in contacts
            ],
            "count": len(contacts),
        }

    async def get_contact_timeline(self, args: ToolArguments) -> dict[str, object]:
        contact_id = int(args["contact_id"])
        contact = await self.context.db.scalar(
            select_workspace_owned(Contact, self.context.workspace_id, Contact.id == contact_id)
        )
        if contact is None:
            return {"success": False, "error": "Contact not found"}
        events = await read_contact_timeline(
            self.context.db,
            workspace_id=self.context.workspace_id,
            contact_id=contact_id,
        )
        return {"success": True, "data": format_contact_timeline(events)}

    async def record_contact_note(self, args: ToolArguments) -> dict[str, object]:
        """Store an approved contact fact, never an instruction to other agents."""
        contact_id = int(args["contact_id"])
        contact = await self.context.db.scalar(
            select_workspace_owned(Contact, self.context.workspace_id, Contact.id == contact_id)
        )
        if contact is None:
            return {"success": False, "error": "Contact not found"}
        note = str(args["note"]).strip()[:500]
        if not note:
            return {"success": False, "error": "Note is empty"}
        await record_event(
            self.context.db,
            workspace_id=self.context.workspace_id,
            contact_id=contact_id,
            source="crm_note",
            source_id=str(self.context.approved_action_id or uuid.uuid4()),
            channel="crm",
            summary=note,
            occurred_at=datetime.now(UTC),
        )
        return {"success": True}

    async def create_contact(self, args: ToolArguments) -> dict[str, object]:
        phone = args["phone"]
        existing = await self.context.db.execute(
            select_workspace_owned(
                Contact,
                self.context.workspace_id,
                Contact.phone_number == phone,
            )
        )
        if existing.scalar_one_or_none():
            return {"success": False, "error": "Contact with this phone already exists"}

        contact = Contact(
            workspace_id=self.context.workspace_id,
            first_name=args["first_name"],
            last_name=args.get("last_name"),
            phone_number=phone,
            email=args.get("email"),
            notes=args.get("notes"),
        )
        self.context.db.add(contact)
        await self.context.db.flush()

        return {
            "success": True,
            "data": {
                "id": contact.id,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "phone": contact.phone_number,
            },
        }

    async def get_today_queue(self, _args: ToolArguments) -> dict[str, object]:
        """Ordered Today mission queue: approvals, nudges, batches, drafts, gaps."""
        queue = await TodayQueueService(self.context.db).get_today_queue(self.context.workspace_id)
        return {
            "success": True,
            "data": {
                "generated_at": queue.generated_at.isoformat(),
                "items": [item.model_dump() for item in queue.items],
            },
            "count": len(queue.items),
        }

    async def get_dashboard_stats(self, _args: ToolArguments) -> dict[str, object]:
        contacts_count = await self.context.db.scalar(
            select_workspace_owned(Contact, self.context.workspace_id)
            .with_only_columns(func.count())
            .select_from(Contact)
        )
        campaigns_count = await self.context.db.scalar(
            select_workspace_owned(Campaign, self.context.workspace_id)
            .with_only_columns(func.count())
            .select_from(Campaign)
        )
        conversations_count = await self.context.db.scalar(
            select_workspace_owned(Conversation, self.context.workspace_id)
            .with_only_columns(func.count())
            .select_from(Conversation)
        )
        appointments_count = await self.context.db.scalar(
            select_workspace_owned(
                Appointment,
                self.context.workspace_id,
                Appointment.scheduled_at >= datetime.now(UTC),
            )
            .with_only_columns(func.count())
            .select_from(Appointment)
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
