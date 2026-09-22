"""Unit tests for the first-touch opener optimizer.

Cover the pure ranking/aggregation/scoring logic and the offline (agent-driven)
report path with no DB or network: stage normalization, the outcome-weighted
opener score, per-opener aggregation + ranking, reproducible fingerprints, and
input validation.
"""

import pytest

from app.services.ai.roleplay.opener_optimizer import (
    STAGE_POINTS,
    OpenerCandidate,
    build_outcome,
    build_report_from_outcomes,
    compute_opener_score,
    config_fingerprint,
    normalize_stage,
)

OPENERS = [
    OpenerCandidate(id="strong", text="Test 100+ ad variations from one recording.", strategy="v"),
    OpenerCandidate(id="weak", text="Are you still running ads?", strategy="q"),
]
PERSONAS = ["prestyj-a", "prestyj-b"]


def _row(opener_id: str, persona: str, **kw: object) -> dict[str, object]:
    base = {"opener_id": opener_id, "persona_slug": persona, "repeat": 0}
    base.update(kw)
    return base


def test_normalize_stage_defaults_unknown_to_disengaged() -> None:
    assert normalize_stage("engaged") == "engaged"
    assert normalize_stage("AGREED_TO_BUY") == "agreed_to_buy"
    assert normalize_stage("nonsense") == "disengaged"
    assert normalize_stage(None) == "disengaged"


def test_compute_opener_score_is_outcome_weighted() -> None:
    # Stage dominates; full close + full intent + full craft == 100.
    assert compute_opener_score(STAGE_POINTS["agreed_to_buy"], 100, 100) == 100.0
    assert compute_opener_score(STAGE_POINTS["disengaged"], 0, 0) == 0.0
    # A higher funnel stage must outscore a lower one at equal sub-scores.
    engaged = compute_opener_score(STAGE_POINTS["engaged"], 50, 50)
    replied = compute_opener_score(STAGE_POINTS["replied"], 50, 50)
    assert engaged > replied


def test_build_outcome_derives_close_from_stage_and_clamps() -> None:
    outcome = build_outcome(
        opener_id="strong",
        persona_slug="prestyj-a",
        repeat=0,
        raw={
            "stage": "agreed_to_buy",
            "buying_intent": 150,  # clamps to 100
            "opener_craft": -5,  # clamps to 0
            "reached_close": False,  # forced True by stage
            "agreed_pack": "500",
        },
    )
    assert outcome.reached_close is True
    assert outcome.buying_intent == 100.0
    assert outcome.opener_craft == 0.0
    assert outcome.agreed_pack == "500"


def test_ranking_orders_by_outcome_and_aggregates() -> None:
    rows = []
    for persona in PERSONAS:
        rows.append(
            _row(
                "strong",
                persona,
                stage="agreed_to_buy",
                buying_intent=90,
                opener_craft=85,
                agreed_pack="300",
            )
        )
        rows.append(
            _row("weak", persona, stage="replied", buying_intent=30, opener_craft=40),
        )

    report = build_report_from_outcomes(
        rows=rows,
        openers=OPENERS,
        persona_slugs=PERSONAS,
        workspace_id="ws-1",
        agent_name="Closer",
        agent_system_prompt="SYS",
        conversations_per_persona=1,
        max_turns=3,
    )

    assert report.total_conversations == 4
    assert report.generator == "agent"
    assert [a.candidate.id for a in report.rankings] == ["strong", "weak"]

    winner = report.rankings[0]
    assert winner.reply_rate == 1.0
    assert winner.engaged_rate == 1.0
    assert winner.agreed_rate == 1.0
    assert winner.agreed_packs == {"300": 2}
    assert winner.per_persona_mean_score.keys() == {"prestyj-a", "prestyj-b"}

    loser = report.rankings[1]
    assert loser.agreed_rate == 0.0
    assert loser.engaged_rate == 0.0
    assert loser.mean_score < winner.mean_score


def test_fingerprint_is_reproducible_and_config_sensitive() -> None:
    kwargs = {
        "openers": OPENERS,
        "persona_slugs": PERSONAS,
        "conversations_per_persona": 2,
        "max_turns": 3,
        "prospect_model": "agent",
        "scorer_model": "agent",
        "base_seed": 42,
        "agent_prompt": "DURABLE PROMPT",
    }
    fp1 = config_fingerprint(**kwargs)  # type: ignore[arg-type]
    fp2 = config_fingerprint(**kwargs)  # type: ignore[arg-type]
    assert fp1 == fp2

    changed = dict(kwargs)
    changed["base_seed"] = 43
    assert config_fingerprint(**changed) != fp1  # type: ignore[arg-type]


def test_prompt_identity_decouples_fingerprint_from_runtime_prompt() -> None:
    rows = [_row("strong", "prestyj-a", stage="engaged", buying_intent=60, opener_craft=70)]
    common = {
        "rows": rows,
        "openers": OPENERS,
        "persona_slugs": PERSONAS,
        "workspace_id": "ws-1",
        "agent_name": "Closer",
        "conversations_per_persona": 1,
        "max_turns": 3,
        "prompt_identity": "DURABLE",
    }
    # Different runtime prompts (e.g. embedded clock) but same durable identity
    # must yield the same fingerprint.
    r1 = build_report_from_outcomes(agent_system_prompt="RUNTIME @ 08:00", **common)  # type: ignore[arg-type]
    r2 = build_report_from_outcomes(agent_system_prompt="RUNTIME @ 09:00", **common)  # type: ignore[arg-type]
    assert r1.config_fingerprint == r2.config_fingerprint


def test_unknown_opener_or_persona_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown opener_id"):
        build_report_from_outcomes(
            rows=[_row("ghost", "prestyj-a", stage="engaged")],
            openers=OPENERS,
            persona_slugs=PERSONAS,
            workspace_id="ws-1",
            agent_name="Closer",
            agent_system_prompt="SYS",
            conversations_per_persona=1,
            max_turns=3,
        )
    with pytest.raises(ValueError, match="unknown persona_slug"):
        build_report_from_outcomes(
            rows=[_row("strong", "ghost", stage="engaged")],
            openers=OPENERS,
            persona_slugs=PERSONAS,
            workspace_id="ws-1",
            agent_name="Closer",
            agent_system_prompt="SYS",
            conversations_per_persona=1,
            max_turns=3,
        )
