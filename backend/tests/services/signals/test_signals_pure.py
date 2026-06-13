"""Pure-unit tests for the buying-signal layer (no DB)."""

from __future__ import annotations

from app.models.prospect_signal import ProspectSignalType
from app.services.signals.aggregator import SignalAggregator
from app.services.signals.providers.ad_tech import signal_from_pixels
from app.services.signals.types import CollectedSignal


class _Prospect:
    """Lightweight stand-in for a LeadProspect for static-method tests."""

    def __init__(self, lead_score: int = 0, evidence: list | None = None) -> None:
        self.lead_score = lead_score
        self.evidence = evidence if evidence is not None else []


class TestCollectedSignal:
    def test_strength_is_clamped(self) -> None:
        assert CollectedSignal("x", 250, "src").strength == 100
        assert CollectedSignal("x", -5, "src").strength == 0

    def test_default_evidence_blob(self) -> None:
        blob = CollectedSignal("running_ads", 80, "ad_library", summary="hi").evidence_blob()
        assert blob["type"] == "signal"
        assert blob["signal_type"] == "running_ads"
        assert blob["strength"] == 80
        assert blob["summary"] == "hi"


class TestSignalFromPixels:
    def test_ad_pixels_produce_strong_signal(self) -> None:
        signal = signal_from_pixels({"meta_pixel": True, "google_ads": True})
        assert signal is not None
        assert signal.signal_type == ProspectSignalType.AD_TECH.value
        assert signal.strength == 70
        assert signal.payload["has_ad_pixel"] is True

    def test_analytics_only_is_weaker_and_not_ad_pixel(self) -> None:
        signal = signal_from_pixels({"google_analytics": True})
        assert signal is not None
        assert signal.payload["has_ad_pixel"] is False
        assert signal.strength == 10

    def test_strength_capped_at_100(self) -> None:
        signal = signal_from_pixels(
            {
                "meta_pixel": True,
                "google_ads": True,
                "tiktok_pixel": True,
                "linkedin_pixel": True,
                "gtm": True,
            }
        )
        assert signal is not None
        assert signal.strength == 100

    def test_no_pixels_returns_none(self) -> None:
        assert signal_from_pixels({}) is None
        assert signal_from_pixels({"meta_pixel": False}) is None


class TestAggregatorFolding:
    def test_fold_takes_max_strength(self) -> None:
        prospect = _Prospect(lead_score=40)
        signals = [
            CollectedSignal("running_ads", 75, "ad_library"),
            CollectedSignal("ad_tech", 35, "website"),
        ]
        SignalAggregator._fold_into_score(prospect, signals)  # type: ignore[arg-type]
        assert prospect.lead_score == 75

    def test_fold_is_monotonic(self) -> None:
        prospect = _Prospect(lead_score=90)
        SignalAggregator._fold_into_score(  # type: ignore[arg-type]
            prospect, [CollectedSignal("ad_tech", 35, "website")]
        )
        assert prospect.lead_score == 90

    def test_append_evidence_replaces_same_type_source(self) -> None:
        prospect = _Prospect(
            evidence=[
                {"type": "signal", "signal_type": "ad_tech", "source": "website", "strength": 10},
                {"type": "person_extraction", "source": "web_people"},
            ]
        )
        SignalAggregator._append_evidence(  # type: ignore[arg-type]
            prospect, [CollectedSignal("ad_tech", 70, "website")]
        )
        signal_items = [e for e in prospect.evidence if e.get("type") == "signal"]
        # Old ad_tech/website signal replaced, not duplicated.
        assert len(signal_items) == 1
        assert signal_items[0]["strength"] == 70
        # Non-signal evidence is preserved.
        assert any(e.get("type") == "person_extraction" for e in prospect.evidence)
