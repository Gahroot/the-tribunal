"""Protocol + abstract base for source-agnostic lead discovery providers.

A provider is anything that, given a :class:`LeadDiscoveryRequest`, can
produce a :class:`ProviderResult` worth of normalized candidates. Concrete
implementations wrap third-party APIs (Google Places, Apollo, etc.), local
imports (CSV, manual seed), or future LLM-driven sources.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from app.services.lead_discovery.types import LeadDiscoveryRequest, ProviderResult


@runtime_checkable
class LeadDiscoveryProvider(Protocol):
    """Structural interface every discovery provider must satisfy."""

    source_type: str
    """Identifier matching ``DiscoverySourceType`` (``"google_places"``)."""

    async def search(self, request: LeadDiscoveryRequest) -> ProviderResult:
        """Run one discovery query and return a normalized result.

        Implementations:
            * Map every native record into :class:`RawLead`.
            * Apply within-batch dedupe (see
              :func:`app.services.lead_discovery.dedupe.dedupe_raw_leads`).
            * Raise :class:`LeadDiscoveryProviderError` on hard failures.
            * Capture soft failures via :class:`DiscoveryWarning`.
        """
        ...

    async def close(self) -> None:
        """Release any pooled resources (HTTP clients, sockets)."""
        ...


class BaseLeadDiscoveryProvider:
    """Convenience base class for providers running in-process.

    Provides:

    * A typed ``source_type`` class attribute so subclasses can't forget it.
    * A no-op default ``close()`` for providers that hold no resources.
    """

    source_type: ClassVar[str]

    async def search(
        self, request: LeadDiscoveryRequest
    ) -> ProviderResult:  # pragma: no cover - abstract
        raise NotImplementedError

    async def close(self) -> None:
        """Default to no-op; subclasses with HTTP clients should override."""
        return None
