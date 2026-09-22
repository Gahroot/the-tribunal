"""Tests for the reproducible Prestyj Batch Video Ads knowledge seed."""

from __future__ import annotations

from app.services.knowledge.prestyj_batch_video_ads import (
    PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS,
    PRESTYJ_BATCH_VIDEO_ADS_RETRIEVAL_CHECKS,
    all_seed_text,
)
from app.services.offers.prestyj_batch_video_ads import (
    PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS,
)


def test_seed_documents_cover_required_product_facts() -> None:
    text = all_seed_text()

    assert "100 ads: $497 total for 100 ads = $4.97 per ad" in text
    assert "300 ads: $1,497 total for 300 ads = $4.99 per ad" in text
    assert "500 ads: $2,500 total for 500 ads = $5.00 per ad" in text
    assert "1,000 ads: $3,997 total for 1,000 ads = $4.00 per ad" in text
    assert "1–2 business days" in text
    assert "teleprompter" in text
    assert "9:16, captioned" in text
    assert "Andromeda" in text
    assert "creative is the targeting input" in text


def test_seed_documents_make_escalation_exclusions_explicit() -> None:
    text = all_seed_text()

    for exclusion in (
        "No media buying",
        "No ad-account management",
        "No campaign setup inside Meta, TikTok, or YouTube",
        "No AI-agent install",
        "No consulting or ongoing campaign management",
    ):
        assert exclusion in text

    assert "Escalate ONLY when the buyer wants add-ons beyond the batch" in text


def test_seed_documents_include_head_to_head_objection_answers() -> None:
    text = all_seed_text()

    assert 'Objection: "Why not just hire a UGC creator?"' in text
    assert "creative system built for the volume modern paid platforms require" in text
    assert 'Objection: "Why not use a creative agency?"' in text
    assert "cost per ad around $4–$5" in text
    assert "Do not promise CTR, ROAS, appointments" in text
    assert "revenue because those depend on the offer" in text


def test_retrieval_checks_are_backed_by_seed_text() -> None:
    text = all_seed_text()

    for check in PRESTYJ_BATCH_VIDEO_ADS_RETRIEVAL_CHECKS:
        for expected_term in check.expected_terms:
            assert expected_term in text


def test_each_seed_document_has_stable_metadata_inputs() -> None:
    keys = [document.key for document in PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS]

    assert len(keys) == len(set(keys))
    assert all(key.startswith("prestyj_batch_video_ads:") for key in keys)
    assert all(document.priority > 0 for document in PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS)
    assert [pack["ad_count"] for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS] == [
        100,
        300,
        500,
        1000,
    ]
