"""Discovery-provider exceptions.

Providers raise these when they cannot complete a request at all. Soft, partial
failures are reported via ``ProviderResult.warnings`` instead.
"""

from __future__ import annotations


class LeadDiscoveryProviderError(Exception):
    """Hard failure from a discovery provider.

    The discovery job state machine wraps this into a ``failed`` record. Sub-
    classes carry richer intent for ops dashboards and retry policy.
    """


class LeadDiscoveryAuthError(LeadDiscoveryProviderError):
    """Provider rejected the configured credentials (401 / 403)."""


class LeadDiscoveryRateLimitError(LeadDiscoveryProviderError):
    """Provider returned a quota / rate-limit response (429 or equivalent)."""
