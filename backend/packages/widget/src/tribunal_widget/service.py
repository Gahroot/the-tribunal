"""Business behavior for unauthenticated public embed endpoints."""

import structlog
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core_api import derive_outbound_key, hash_phone, settings
from app.models.agent import Agent
from app.models.contact import Contact
from app.models.demo_request import DemoRequest
from app.services.sla.speed_to_lead import enqueue_speed_to_lead_job

from .access import EmbedAccessService
from .openai import EmbedOpenAIService
from .providers import make_sms_sender, make_voice_caller
from .schemas import (
    ChatRequest,
    ChatResponse,
    EmbedActionResponse,
    EmbedConfigResponse,
    EmbedPhoneRequest,
    TokenResponse,
    ToolCallRequest,
    ToolCallResponse,
    TranscriptRequest,
    TranscriptResponse,
)

logger = structlog.get_logger()


class PublicEmbedService:
    """Coordinate public embed config, chat, voice, text, and telemetry behavior."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.access = EmbedAccessService(db)
        self.openai = EmbedOpenAIService(db)
        self.log = logger.bind(component="public_embed_service")

    async def get_agent_by_public_id(self, public_id: str) -> Agent:
        """Return an active embed-enabled agent by public ID or raise 404."""
        result = await self.db.execute(
            select(Agent).where(
                Agent.public_id == public_id,
                Agent.embed_enabled.is_(True),
                Agent.is_active.is_(True),
            )
        )
        agent: Agent | None = result.scalar_one_or_none()

        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or embedding not enabled",
            )

        return agent

    async def get_config(self, *, public_id: str, origin: str | None) -> EmbedConfigResponse:
        """Return public embed configuration after origin validation."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)
        embed_settings = agent.embed_settings or {}

        return EmbedConfigResponse(
            public_id=agent.public_id or "",
            name=agent.name,
            greeting_message=agent.initial_greeting,
            button_text=embed_settings.get("button_text", "Talk to AI"),
            theme=embed_settings.get("theme", "auto"),
            position=embed_settings.get("position", "bottom-right"),
            primary_color=embed_settings.get("primary_color", "#6366f1"),
            language=agent.language,
            voice=agent.voice_id,
            channel_mode=agent.channel_mode,
        )

    async def create_realtime_token(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
    ) -> TokenResponse:
        """Validate, rate-limit, and mint an OpenAI Realtime token."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)
        await self.access.enforce_token_limit(client_ip=client_ip, public_id=public_id)
        return await self.openai.create_realtime_token(agent)

    async def send_chat_message(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
        body: ChatRequest,
    ) -> ChatResponse:
        """Validate, rate-limit, and answer a public embed chat message."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)
        await self.access.enforce_chat_limit(client_ip=client_ip, public_id=public_id)
        return await self.openai.send_chat_message(agent, body)

    async def execute_tool_call(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
        body: ToolCallRequest,
    ) -> ToolCallResponse:
        """Validate, rate-limit, and execute a public embed tool call."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)
        await self.access.enforce_chat_limit(client_ip=client_ip, public_id=public_id)

        if body.tool_name == "end_call":
            return ToolCallResponse(
                success=True,
                action="end_call",
                message="Call ended successfully",
            )

        if body.tool_name == "request_phone_demo":
            if not _agent_has_enabled_tool(agent, "request_phone_demo"):
                return ToolCallResponse(
                    success=False,
                    action="request_phone_demo",
                    message="Phone demo requests are not enabled for this agent.",
                    result={"error": "tool_not_enabled"},
                )

            try:
                phone_request = EmbedPhoneRequest.model_validate(body.arguments)
            except ValidationError:
                return ToolCallResponse(
                    success=False,
                    action="request_phone_demo",
                    message="Please provide a valid 10-digit US phone number before I can call.",
                    result={"error": "invalid_phone_request"},
                )

            try:
                call_response = await self.trigger_call(
                    public_id=public_id,
                    origin=origin,
                    client_ip=client_ip,
                    body=phone_request,
                )
            except HTTPException as exc:
                detail = (
                    exc.detail if isinstance(exc.detail, str) else "Unable to start the phone demo."
                )
                return ToolCallResponse(
                    success=False,
                    action="request_phone_demo",
                    message=detail,
                    result={"error": "phone_demo_failed", "status_code": exc.status_code},
                )

            return ToolCallResponse(
                success=call_response.success,
                action="request_phone_demo",
                message=call_response.message,
            )

        return ToolCallResponse(
            success=False,
            action=body.tool_name,
            message=f"Tool {body.tool_name} is not available for this agent.",
            result={"error": "unknown_tool"},
        )

    async def save_transcript(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
        body: TranscriptRequest,
    ) -> TranscriptResponse:
        """Validate, rate-limit, and log a public embed transcript."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)
        await self.access.enforce_chat_limit(client_ip=client_ip, public_id=public_id)

        self.log.info(
            "embed_transcript_saved",
            public_id=public_id,
            workspace_id=str(agent.workspace_id),
            session_id=body.session_id,
            duration_seconds=body.duration_seconds,
            transcript_length=len(body.transcript),
        )
        return TranscriptResponse(status="saved")

    async def trigger_call(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
        body: EmbedPhoneRequest,
    ) -> EmbedActionResponse:
        """Validate, rate-limit, create contact metadata, and start an embed call."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)

        if not settings.telnyx_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Voice service not available",
            )

        await self.access.enforce_phone_limit(client_ip=client_ip, phone_number=body.phone_number)
        created_contact_id = await self._upsert_contact_from_phone_request(agent, body)
        demo_record = await self._record_demo_request(
            phone_number=body.phone_number,
            request_type="embed_call",
            client_ip=client_ip,
        )

        voice_service = make_voice_caller()
        try:
            api_base = settings.api_base_url or "https://example.com"
            webhook_url = f"{api_base}/webhooks/telnyx/voice"
            connection_id = settings.telnyx_connection_id if settings.telnyx_connection_id else None
            idempotency_key = derive_outbound_key("embed_call", demo_record.id)
            await voice_service.initiate_call(
                to_number=body.phone_number,
                from_number=settings.demo_from_phone_number,
                connection_id=connection_id,
                webhook_url=webhook_url,
                db=self.db,
                workspace_id=agent.workspace_id,
                contact_phone=body.phone_number,
                agent_id=agent.id,
                idempotency_key=idempotency_key,
            )

            demo_record.status = "initiated"
            await self.db.commit()
            # embed_call above already placed the voice attempt for this lead;
            # enqueue only the parallel "we're calling you now" SMS, and only
            # when this request actually created a brand-new contact.
            if created_contact_id is not None:
                await enqueue_speed_to_lead_job(
                    workspace_id=agent.workspace_id,
                    contact_id=created_contact_id,
                    source="widget",
                    channels=("sms",),
                )
            return EmbedActionResponse(
                success=True,
                message="Call initiated! You should receive a call within 10 seconds.",
            )
        except Exception as exc:
            demo_record.status = "failed"
            demo_record.error_message = str(exc)[:500]
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate call. Please try again.",
            ) from exc
        finally:
            await voice_service.close()

    async def trigger_text(
        self,
        *,
        public_id: str,
        origin: str | None,
        client_ip: str,
        body: EmbedPhoneRequest,
    ) -> EmbedActionResponse:
        """Validate, rate-limit, and send the embed greeting over SMS."""
        agent = await self.get_agent_by_public_id(public_id)
        self.access.require_origin(origin, agent.allowed_domains)

        if not settings.telnyx_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SMS service not available",
            )

        await self.access.enforce_phone_limit(client_ip=client_ip, phone_number=body.phone_number)
        demo_record = await self._record_demo_request(
            phone_number=body.phone_number,
            request_type="embed_text",
            client_ip=client_ip,
        )

        default_greeting = f"Hi! Thanks for reaching out to {agent.name}. How can I help you today?"
        greeting = agent.initial_greeting or default_greeting
        sms_service = make_sms_sender()
        try:
            idempotency_key = derive_outbound_key("embed_text", demo_record.id)
            await sms_service.send_message(
                to_number=body.phone_number,
                from_number=settings.demo_from_phone_number,
                body=greeting,
                db=self.db,
                workspace_id=agent.workspace_id,
                agent_id=agent.id,
                idempotency_key=idempotency_key,
            )

            demo_record.status = "initiated"
            await self.db.commit()
            return EmbedActionResponse(
                success=True,
                message="Text sent! Check your phone for a message.",
            )
        except Exception as exc:
            demo_record.status = "failed"
            demo_record.error_message = str(exc)[:500]
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send text. Please try again.",
            ) from exc
        finally:
            await sms_service.close()

    async def _record_demo_request(
        self,
        *,
        phone_number: str,
        request_type: str,
        client_ip: str,
    ) -> DemoRequest:
        """Persist an embed call/text request for auditing and rate-limit history."""
        demo_record = DemoRequest(
            phone_number=phone_number,
            request_type=request_type,
            client_ip=client_ip,
        )
        self.db.add(demo_record)
        await self.db.flush()
        return demo_record

    async def _upsert_contact_from_phone_request(
        self,
        agent: Agent,
        body: EmbedPhoneRequest,
    ) -> int | None:
        """Create or update a contact from optional public embed form fields.

        Returns the new contact's id when this request created a lead contact,
        else None (no identifying fields supplied, or it already existed).
        """
        if not body.caller_name and not body.notes:
            return None

        contact_result = await self.db.execute(
            select(Contact).where(
                Contact.workspace_id == agent.workspace_id,
                Contact.phone_hash == hash_phone(body.phone_number),
            )
        )
        contact = contact_result.scalar_one_or_none()
        created_contact = False

        if contact is not None:
            if body.caller_name:
                first_name, last_name = _split_caller_name(body.caller_name)
                contact.first_name = first_name
                if last_name is not None:
                    contact.last_name = last_name
            if body.notes:
                contact.notes = body.notes
        else:
            first_name = "Demo Visitor"
            last_name = None
            if body.caller_name:
                first_name, last_name = _split_caller_name(body.caller_name)

            contact = Contact(
                workspace_id=agent.workspace_id,
                first_name=first_name,
                last_name=last_name,
                phone_number=body.phone_number,
                phone_hash=hash_phone(body.phone_number),
                notes=body.notes,
                source="embed_demo",
            )
            self.db.add(contact)
            created_contact = True

        await self.db.flush()
        return contact.id if created_contact else None


def _agent_has_enabled_tool(agent: Agent, tool_name: str) -> bool:
    """Return whether an agent explicitly enables a public embed tool."""
    enabled_tools = getattr(agent, "enabled_tools", None)
    if not isinstance(enabled_tools, (list, tuple, set, frozenset)):
        return False
    return tool_name in enabled_tools


def _split_caller_name(caller_name: str) -> tuple[str, str | None]:
    """Split a caller name into first and optional last name."""
    parts = caller_name.strip().split(" ", 1)
    first_name = parts[0] if parts and parts[0] else "Demo Visitor"
    last_name = parts[1] if len(parts) > 1 else None
    return first_name, last_name
