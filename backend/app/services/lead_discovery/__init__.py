"""Source-agnostic lead discovery package.

Lead miner missions can pull candidate prospects from many sources (Google
Places, web scraping, CSV uploads, manual seeds, etc.). This package defines
the shared protocol, normalized data types, dedupe helpers, and the concrete
providers that wrap third-party services.

The existing Find Leads flow continues to use
``app.services.scraping.google_places.GooglePlacesService`` directly; this
package is additive — a new provider abstraction the lead miner builds on.
"""

from app.services.lead_discovery.dedupe import (
    dedupe_key_for_email,
    dedupe_key_for_lead,
    dedupe_key_for_owner_name,
    dedupe_key_for_person,
    dedupe_key_for_phone,
    dedupe_key_for_website,
    dedupe_raw_leads,
    extract_host,
    normalize_email_for_dedupe,
    normalize_owner_name_for_dedupe,
    normalize_phone_for_dedupe,
    normalize_website_host_for_dedupe,
)
from app.services.lead_discovery.errors import (
    LeadDiscoveryAuthError,
    LeadDiscoveryProviderError,
    LeadDiscoveryRateLimitError,
)
from app.services.lead_discovery.protocol import (
    BaseLeadDiscoveryProvider,
    LeadDiscoveryProvider,
)
from app.services.lead_discovery.providers.google_places import (
    GooglePlacesLeadProvider,
)
from app.services.lead_discovery.types import (
    DiscoveryWarning,
    LeadDiscoveryRequest,
    ProviderResult,
    RawLead,
)

__all__ = [
    "BaseLeadDiscoveryProvider",
    "DiscoveryWarning",
    "GooglePlacesLeadProvider",
    "LeadDiscoveryAuthError",
    "LeadDiscoveryProvider",
    "LeadDiscoveryProviderError",
    "LeadDiscoveryRateLimitError",
    "LeadDiscoveryRequest",
    "ProviderResult",
    "RawLead",
    "dedupe_key_for_email",
    "dedupe_key_for_lead",
    "dedupe_key_for_owner_name",
    "dedupe_key_for_person",
    "dedupe_key_for_phone",
    "dedupe_key_for_website",
    "dedupe_raw_leads",
    "extract_host",
    "normalize_email_for_dedupe",
    "normalize_owner_name_for_dedupe",
    "normalize_phone_for_dedupe",
    "normalize_website_host_for_dedupe",
]
