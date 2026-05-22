"""Concrete lead-discovery providers.

Each module exposes one provider class implementing
:class:`app.services.lead_discovery.LeadDiscoveryProvider`.
"""

from app.services.lead_discovery.providers.google_places import (
    GooglePlacesLeadProvider,
)

__all__ = ["GooglePlacesLeadProvider"]
