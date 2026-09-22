"""Tests for OpenAI Realtime session configuration helpers."""

from app.services.ai.openai_realtime_config import (
    DEFAULT_GPT_LIVE_MODEL,
    build_realtime_audio_config,
    build_realtime_session_config,
    extract_realtime_client_secret_value,
    model_supports_realtime_reasoning,
    normalize_realtime_model,
    normalize_reasoning_effort,
    normalize_transcription_language,
)


def test_normalize_transcription_language_maps_locale_to_primary_subtag() -> None:
    """OpenAI Realtime transcription accepts language codes, not app locales."""
    assert normalize_transcription_language("en-US") == "en"
    assert normalize_transcription_language("es_MX") == "es"


def test_normalize_transcription_language_preserves_supported_code() -> None:
    assert normalize_transcription_language("pt") == "pt"


def test_normalize_transcription_language_omits_unsupported_locale() -> None:
    assert normalize_transcription_language("x-klingon") is None
    assert normalize_transcription_language("") is None


def test_build_realtime_audio_config_uses_normalized_transcription_language() -> None:
    audio_config = build_realtime_audio_config(language="en-US")

    assert audio_config["input"]["transcription"] == {
        "model": "gpt-4o-mini-transcribe",
        "language": "en",
    }


def test_build_realtime_audio_config_omits_unsupported_transcription_language() -> None:
    audio_config = build_realtime_audio_config(language="x-klingon")

    assert audio_config["input"]["transcription"] == {"model": "gpt-4o-mini-transcribe"}


def test_extract_realtime_client_secret_value_accepts_current_response_shape() -> None:
    assert extract_realtime_client_secret_value({"value": " ek-test "}) == "ek-test"


def test_extract_realtime_client_secret_value_accepts_legacy_nested_shape() -> None:
    assert (
        extract_realtime_client_secret_value({"client_secret": {"value": "ek-nested"}})
        == "ek-nested"
    )


def test_extract_realtime_client_secret_value_rejects_incomplete_payload() -> None:
    assert extract_realtime_client_secret_value({"client_secret": {}}) is None


# --- GPT Live / gpt-realtime-2.1 reasoning support ---------------------------


def test_gpt_live_default_model_supports_reasoning() -> None:
    """The GPT Live agent type maps to a reasoning-capable Realtime model."""
    assert DEFAULT_GPT_LIVE_MODEL == "gpt-realtime-2.1"
    assert model_supports_realtime_reasoning(DEFAULT_GPT_LIVE_MODEL)


def test_model_supports_reasoning_covers_realtime_2_family() -> None:
    assert model_supports_realtime_reasoning("gpt-realtime-2")
    assert model_supports_realtime_reasoning("gpt-realtime-2.1")
    assert model_supports_realtime_reasoning("gpt-realtime-2.1-mini")
    assert model_supports_realtime_reasoning("gpt-realtime-2-2025-12-15")
    # Non-reasoning realtime models must not opt into reasoning config.
    assert not model_supports_realtime_reasoning("gpt-realtime")
    assert not model_supports_realtime_reasoning("gpt-realtime-mini")


def test_normalize_realtime_model_accepts_known_and_snapshots() -> None:
    assert normalize_realtime_model("gpt-realtime-2.1") == "gpt-realtime-2.1"
    assert normalize_realtime_model("gpt-realtime-2.1-mini") == "gpt-realtime-2.1-mini"
    assert normalize_realtime_model("gpt-realtime-2.1-2026-07-06") == "gpt-realtime-2.1-2026-07-06"


def test_normalize_realtime_model_rejects_unknown_and_non_str() -> None:
    assert normalize_realtime_model("totally-made-up") is None
    assert normalize_realtime_model(None) is None
    assert normalize_realtime_model("") is None
    assert normalize_realtime_model(object()) is None  # type: ignore[arg-type]


def test_normalize_reasoning_effort_normalizes_and_defaults() -> None:
    assert normalize_reasoning_effort("XHIGH") == "xhigh"
    assert normalize_reasoning_effort(" Medium ") == "medium"
    assert normalize_reasoning_effort(None) == "low"
    assert normalize_reasoning_effort("not-a-level") == "low"


def test_build_session_config_sets_reasoning_effort_for_gpt_live() -> None:
    session = build_realtime_session_config(
        instructions="hi",
        model="gpt-realtime-2.1",
        reasoning_effort="high",
    )
    assert session["model"] == "gpt-realtime-2.1"
    assert session["reasoning"] == {"effort": "high"}


def test_build_session_config_omits_reasoning_for_non_reasoning_model() -> None:
    session = build_realtime_session_config(
        instructions="hi",
        model="gpt-realtime",
        reasoning_effort="high",
    )
    assert "reasoning" not in session
