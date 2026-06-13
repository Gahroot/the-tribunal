"""Run signal providers, persist normalized rows, fold strength into score.

The aggregator is the only place that writes
:class:`~app.models.prospect_signal.ProspectSignal` rows. It:

1. Runs every enabled :class:`SignalProvider` against the prospect.
2. Upserts one row per ``(workspace_id, prospect_id, signal_type)`` — re-runs
   refresh strength/payload rather than duplicating.
3. Folds the strongest signal into ``LeadProspect.lead_score`` (monotonic max,
   so re-runs are idempotent).
4. Appends each signal's outreach-ready evidence to ``LeadProspect.evidence``,
   replacing a prior entry of the same ``signal_type`` + ``source``.

It flushes but never commits — the caller owns the transaction boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_prospect import LeadProspect
from app.models.prospect_signal import ProspectSignal, ProspectSignalStatus
from app.services.signals.protocol import SignalProvider
from app.services.signals.types import CollectedSignal

logger = structlog.get_logger()


def _default_providers() -> list[SignalProvider]:
    """Build the default provider set.

    Imported lazily inside the function so importing the aggregator never drags
    in the scraper / ad-intelligence stack unless signals actually run.
    """
    from app.services.signals.providers.ad_tech import AdTechSignalProvider
    from app.services.signals.providers.ads import AdsSignalProvider
    from app.services.signals.providers.funding import FundingSignalProvider
    from app.services.signals.providers.hiring import HiringSignalProvider

    return [
        AdsSignalProvider(),
        AdTechSignalProvider(),
        HiringSignalProvider(),
        FundingSignalProvider(),
    ]


class SignalAggregator:
    """Runs signal providers and persists their normalized output."""

    def __init__(self, providers: list[SignalProvider] | None = None) -> None:
        self._providers = providers if providers is not None else _default_providers()

    @property
    def providers(self) -> list[SignalProvider]:
        return self._providers

    async def run(self, db: AsyncSession, prospect: LeadProspect) -> list[CollectedSignal]:
        """Collect, persist, and fold signals for ``prospect``.

        Returns the collected signals (may be empty). Never raises out of a
        single provider failure — a broken provider is logged and skipped.
        """
        log = logger.bind(component="signal_aggregator", prospect_id=str(prospect.id))
        collected: list[CollectedSignal] = []
        for provider in self._providers:
            if not provider.is_enabled():
                continue
            try:
                signals = await provider.collect(db, prospect)
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                log.warning(
                    "signal_provider_failed",
                    source=getattr(provider, "signal_source", provider.__class__.__name__),
                    error=str(exc),
                )
                continue
            collected.extend(signals)

        if not collected:
            return []

        await self._upsert_rows(db, prospect, collected)
        self._fold_into_score(prospect, collected)
        self._append_evidence(prospect, collected)
        await db.flush()
        log.info("signals_aggregated", count=len(collected))
        return collected

    async def _upsert_rows(
        self,
        db: AsyncSession,
        prospect: LeadProspect,
        signals: list[CollectedSignal],
    ) -> None:
        existing_rows = await db.execute(
            select(ProspectSignal).where(ProspectSignal.prospect_id == prospect.id)
        )
        by_type: dict[str, ProspectSignal] = {
            row.signal_type: row for row in existing_rows.scalars().all()
        }
        now = datetime.now(UTC)
        for signal in signals:
            row = by_type.get(signal.signal_type)
            if row is None:
                db.add(
                    ProspectSignal(
                        workspace_id=prospect.workspace_id,
                        prospect_id=prospect.id,
                        signal_type=signal.signal_type,
                        strength=signal.strength,
                        status=ProspectSignalStatus.ACTIVE,
                        source=signal.source,
                        payload=signal.payload,
                        observed_at=signal.observed_at,
                    )
                )
            else:
                row.strength = signal.strength
                row.status = ProspectSignalStatus.ACTIVE
                row.source = signal.source
                row.payload = signal.payload
                row.observed_at = signal.observed_at or now

    @staticmethod
    def _fold_into_score(prospect: LeadProspect, signals: list[CollectedSignal]) -> None:
        strongest = max(signal.strength for signal in signals)
        prospect.lead_score = max(prospect.lead_score or 0, strongest)

    @staticmethod
    def _append_evidence(prospect: LeadProspect, signals: list[CollectedSignal]) -> None:
        fresh_keys = {(s.signal_type, s.source) for s in signals}
        kept: list[dict[str, Any]] = []
        for item in prospect.evidence or []:
            if (
                item.get("type") == "signal"
                and (
                    item.get("signal_type"),
                    item.get("source"),
                )
                in fresh_keys
            ):
                continue
            kept.append(item)
        kept.extend(signal.evidence_blob() for signal in signals)
        prospect.evidence = kept


async def aggregate_signals(
    db: AsyncSession,
    prospect: LeadProspect,
    *,
    providers: list[SignalProvider] | None = None,
) -> list[CollectedSignal]:
    """Convenience wrapper: run the default (or given) aggregator once."""
    return await SignalAggregator(providers=providers).run(db, prospect)
