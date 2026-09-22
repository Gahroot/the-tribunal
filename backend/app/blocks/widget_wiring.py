"""Host wiring for the ``tribunal-widget`` block.

The widget block (public embeddable chat/voice) imports only the core surface; it
borrows Telnyx SMS/voice (the *voice* block) and OpenAI credential resolution
(the *agent-brain* block) through injection ports declared in
``tribunal_widget.providers``. This module registers the host's concrete
implementations for those ports.

Importing this module registers the providers as a side effect (see the
``register()`` call at the bottom), so any host that imports the v1 API router
gets the block fully wired.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from tribunal_widget.providers import (
    OpenAICredentialError as WidgetCredentialError,
)
from tribunal_widget.providers import (
    register_providers,
)

from app.core.config import settings
from app.services.ai.openai_credentials import (
    OpenAICredentialContext,
    OpenAICredentialError,
    resolve_openai_credentials,
)
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.telephony.telnyx_voice import TelnyxVoiceService


def _make_sms_sender() -> TelnyxSMSService:
    """Build the host's Telnyx SMS client for the block's ``text`` action."""
    return TelnyxSMSService(settings.telnyx_api_key)


def _make_voice_caller() -> TelnyxVoiceService:
    """Build the host's Telnyx voice client for the block's ``call`` action."""
    return TelnyxVoiceService(settings.telnyx_api_key)


async def _resolve_credentials(db: AsyncSession, workspace_id: Any) -> OpenAICredentialContext:
    """Resolve per-workspace OpenAI credentials, translating the error type.

    The block catches its own ``OpenAICredentialError``; the host's resolver
    raises the agent-brain block's error, so re-raise as the block's type to keep
    the block free of an agent-brain import.
    """
    try:
        return await resolve_openai_credentials(db, workspace_id)
    except OpenAICredentialError as exc:
        raise WidgetCredentialError(str(exc)) from exc


def register() -> None:
    """Register the host adapters with the widget block's provider registry."""
    register_providers(
        sms_sender_factory=_make_sms_sender,
        voice_caller_factory=_make_voice_caller,
        credential_resolver=_resolve_credentials,
    )


register()
