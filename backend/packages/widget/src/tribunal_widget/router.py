"""HTTP surface for the ``widget`` block — the public embed endpoints.

``get_router()`` is the only required runtime export. These routes are
unauthenticated by design (public embed widget); each one validates the request
origin against the agent's ``allowed_domains`` and applies IP/phone rate limits,
so no auth or workspace token is exposed to the browser.

Core primitives come only through ``app.core_api`` (DB session, settings) plus
``app.core`` helpers; the block carries no sideways import into sibling blocks.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.utils import get_client_ip
from app.core_api import DB, settings

from .schemas import (
    ChatRequest,
    ChatResponse,
    EmbedActionResponse,
    EmbedConfigResponse,
    EmbedPhoneRequest,
    TokenRequest,
    TokenResponse,
    ToolCallRequest,
    ToolCallResponse,
    TranscriptRequest,
    TranscriptResponse,
)
from .service import PublicEmbedService


def _origin(request: Request) -> str | None:
    """Return the browser Origin header used by public embed validation."""
    return request.headers.get("origin")


def _client_ip(request: Request) -> str:
    """Return the validated caller IP for public embed rate limits."""
    return get_client_ip(request, settings.trusted_proxies)


def get_router() -> APIRouter:
    """Return the block's public embed router for ``include_router(...)``.

    The router carries its own ``/p/embed`` prefix and tag so a host mounts the
    block's entire HTTP surface in one call::

        api_router.include_router(get_router())  # -> /api/v1/p/embed/...
    """
    router = APIRouter(prefix="/p/embed", tags=["Public Embed"])

    @router.get("/{public_id}/config", response_model=EmbedConfigResponse)
    async def get_embed_config(
        public_id: str,
        request: Request,
        db: DB,
    ) -> EmbedConfigResponse:
        """Get public configuration for the embed widget."""
        return await PublicEmbedService(db).get_config(public_id=public_id, origin=_origin(request))

    @router.post("/{public_id}/token", response_model=TokenResponse)
    async def get_ephemeral_token(
        public_id: str,
        request: Request,
        db: DB,
        body: TokenRequest | None = None,
    ) -> TokenResponse:
        """Get an ephemeral token for OpenAI Realtime WebRTC connection."""
        del body
        return await PublicEmbedService(db).create_realtime_token(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
        )

    @router.post("/{public_id}/chat", response_model=ChatResponse)
    async def send_chat_message(
        public_id: str,
        body: ChatRequest,
        request: Request,
        db: DB,
    ) -> ChatResponse:
        """Send a chat message and get AI response."""
        return await PublicEmbedService(db).send_chat_message(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
            body=body,
        )

    @router.post("/{public_id}/tool-call", response_model=ToolCallResponse)
    async def execute_tool_call(
        public_id: str,
        body: ToolCallRequest,
        request: Request,
        db: DB,
    ) -> ToolCallResponse:
        """Execute a tool call from the AI."""
        return await PublicEmbedService(db).execute_tool_call(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
            body=body,
        )

    @router.post("/{public_id}/transcript", response_model=TranscriptResponse)
    async def save_transcript(
        public_id: str,
        body: TranscriptRequest,
        request: Request,
        db: DB,
    ) -> TranscriptResponse:
        """Save a conversation transcript."""
        return await PublicEmbedService(db).save_transcript(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
            body=body,
        )

    @router.post("/{public_id}/call", response_model=EmbedActionResponse)
    async def trigger_embed_call(
        public_id: str,
        body: EmbedPhoneRequest,
        request: Request,
        db: DB,
    ) -> EmbedActionResponse:
        """Trigger an AI call via the embed widget."""
        return await PublicEmbedService(db).trigger_call(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
            body=body,
        )

    @router.post("/{public_id}/text", response_model=EmbedActionResponse)
    async def trigger_embed_text(
        public_id: str,
        body: EmbedPhoneRequest,
        request: Request,
        db: DB,
    ) -> EmbedActionResponse:
        """Trigger an AI text via the embed widget."""
        return await PublicEmbedService(db).trigger_text(
            public_id=public_id,
            origin=_origin(request),
            client_ip=_client_ip(request),
            body=body,
        )

    return router
