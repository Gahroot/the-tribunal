"""Pluggable buying-signal layer for lead prospects.

A *signal* is a typed, queryable reason a prospect is worth contacting now —
they're already running ads, they have ad/analytics tech installed, they're
hiring, they just raised. This package normalizes those into
:class:`~app.models.prospect_signal.ProspectSignal` rows (so the people-search
API can filter/rank in SQL) while still appending the rich, outreach-ready blob
to ``LeadProspect.evidence``.

Layout:

* :mod:`types` — the ``CollectedSignal`` value type providers emit.
* :mod:`protocol` — the ``SignalProvider`` interface + base class.
* :mod:`aggregator` — runs enabled providers, upserts rows, folds strength into
  ``lead_score`` and appends evidence.
* :mod:`providers` — concrete providers (ads, ad-tech, hiring, funding).
"""

from app.services.signals.aggregator import SignalAggregator, aggregate_signals
from app.services.signals.protocol import BaseSignalProvider, SignalProvider
from app.services.signals.types import CollectedSignal

__all__ = [
    "BaseSignalProvider",
    "CollectedSignal",
    "SignalAggregator",
    "SignalProvider",
    "aggregate_signals",
]
