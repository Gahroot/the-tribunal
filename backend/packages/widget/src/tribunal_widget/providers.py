"""Provider ports for the widget block's sibling-capability dependencies.

The block's own code imports **only** the core surface (``app.core_api`` /
``app.core`` / ``app.db`` / ``app.models``). The two capabilities it borrows from
sibling blocks — Telnyx SMS/voice (the *voice* block) and OpenAI credential
resolution (the *agent-brain* block) — are injected by the host through this
small registry, so the block carries no sideways import into those blocks.

A host wires the block once at startup::

    from tribunal_widget.providers import register_providers

    register_providers(
        sms_sender_factory=...,  # () -> SmsSender
        voice_caller_factory=...,  # () -> VoiceCaller
        credential_resolver=...,  # async (db, workspace_id) -> CredentialContext
    )

When a provider is not registered, the corresponding action raises a 503 (for
SMS/voice) or an :class:`OpenAICredentialError` (for credentials), mirroring the
"service not available / not configured" behavior of the host app.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


class OpenAICredentialError(RuntimeError):
    """Raised when usable OpenAI credentials cannot be resolved for an agent."""


@runtime_checkable
class CredentialContext(Protocol):
    """Minimal shape the block needs from a resolved OpenAI credential."""

    # Read-only: the host's context is a frozen dataclass, so the port must not
    # require ``source`` to be settable.
    @property
    def source(self) -> str: ...

    def openai_headers(self) -> dict[str, str]: ...


class SmsSender(Protocol):
    """Outbound SMS port (satisfied by the voice block's ``TelnyxSMSService``)."""

    async def send_message(
        self,
        *,
        to_number: str,
        from_number: str,
        body: str,
        db: AsyncSession,
        workspace_id: Any,
        agent_id: Any,
        idempotency_key: uuid.UUID,
    ) -> Any: ...

    async def close(self) -> None: ...


class VoiceCaller(Protocol):
    """Outbound voice port (satisfied by the voice block's ``TelnyxVoiceService``)."""

    async def initiate_call(
        self,
        *,
        to_number: str,
        from_number: str,
        connection_id: str | None,
        webhook_url: str,
        db: AsyncSession,
        workspace_id: Any,
        contact_phone: str,
        agent_id: Any,
        idempotency_key: uuid.UUID,
    ) -> Any: ...

    async def close(self) -> None: ...


SmsSenderFactory = Callable[[], SmsSender]
VoiceCallerFactory = Callable[[], VoiceCaller]
CredentialResolver = Callable[[AsyncSession, Any], Awaitable[CredentialContext]]

_sms_factory: SmsSenderFactory | None = None
_voice_factory: VoiceCallerFactory | None = None
_credential_resolver: CredentialResolver | None = None


def register_providers(
    *,
    sms_sender_factory: SmsSenderFactory | None = None,
    voice_caller_factory: VoiceCallerFactory | None = None,
    credential_resolver: CredentialResolver | None = None,
) -> None:
    """Register host adapters for the block's injected capabilities.

    Any argument left as ``None`` leaves the corresponding provider untouched, so
    a host may register them in separate calls.
    """
    global _sms_factory, _voice_factory, _credential_resolver
    if sms_sender_factory is not None:
        _sms_factory = sms_sender_factory
    if voice_caller_factory is not None:
        _voice_factory = voice_caller_factory
    if credential_resolver is not None:
        _credential_resolver = credential_resolver


def make_sms_sender() -> SmsSender:
    """Build an SMS sender via the host-registered factory, or 503 when unset."""
    if _sms_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service not available",
        )
    return _sms_factory()


def make_voice_caller() -> VoiceCaller:
    """Build a voice caller via the host-registered factory, or 503 when unset."""
    if _voice_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not available",
        )
    return _voice_factory()


async def resolve_openai_credentials(db: AsyncSession, workspace_id: Any) -> CredentialContext:
    """Resolve OpenAI credentials via the host-registered resolver.

    Raises :class:`OpenAICredentialError` when no resolver is registered or the
    resolver itself cannot produce usable credentials.
    """
    if _credential_resolver is None:
        raise OpenAICredentialError("No OpenAI credential resolver registered")
    return await _credential_resolver(db, workspace_id)
