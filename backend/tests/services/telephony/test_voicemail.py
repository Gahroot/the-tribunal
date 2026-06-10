"""Tests for the AI voicemail pipeline (``app.services.telephony.voicemail``)."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.idempotency import RedisIdempotencyClaim
from app.services.telephony import voicemail as vm

# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #


class _Result:
    def __init__(self, scalar: Any = None, first: Any = None) -> None:
        self._scalar = scalar
        self._first = first

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def first(self) -> Any:
        return self._first


def _make_db(execute_returns: list[Any]) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_returns))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def _patch_session_local(monkeypatch: pytest.MonkeyPatch, *dbs: MagicMock) -> None:
    iterator = iter(dbs)

    def _factory() -> Any:
        db = next(iterator)

        class _CM:
            async def __aenter__(self) -> MagicMock:
                return db

            async def __aexit__(self, *exc: Any) -> None:
                return None

        return _CM()

    monkeypatch.setattr(vm, "AsyncSessionLocal", _factory)


def _make_log() -> MagicMock:
    log = MagicMock()
    log.bind = MagicMock(return_value=log)
    return log


# --------------------------------------------------------------------------- #
# client_state markers
# --------------------------------------------------------------------------- #


def test_encode_and_detect_voicemail_client_state() -> None:
    encoded = vm.encode_voicemail_client_state()
    assert encoded == base64.b64encode(b"voicemail").decode()
    assert vm.is_voicemail_client_state(encoded) is True


@pytest.mark.parametrize(
    "raw",
    [None, "", "not-base64!!", base64.b64encode(b"something-else").decode()],
)
def test_is_voicemail_client_state_rejects_non_markers(raw: str | None) -> None:
    assert vm.is_voicemail_client_state(raw) is False


# --------------------------------------------------------------------------- #
# extract_recording_url
# --------------------------------------------------------------------------- #


def test_extract_recording_url_prefers_public_mp3() -> None:
    payload = {
        "recording_urls": {"mp3": "https://x/auth.mp3"},
        "public_recording_urls": {"mp3": "https://x/public.mp3", "wav": "https://x/public.wav"},
    }
    assert vm.extract_recording_url(payload) == "https://x/public.mp3"


def test_extract_recording_url_falls_back_to_wav_then_recordings_array() -> None:
    assert vm.extract_recording_url({"recording_urls": {"wav": "https://x/a.wav"}}) == (
        "https://x/a.wav"
    )
    payload = {"recordings": [{"public_url": "https://x/r.mp3"}]}
    assert vm.extract_recording_url(payload) == "https://x/r.mp3"


def test_extract_recording_url_returns_none_when_absent() -> None:
    assert vm.extract_recording_url({}) is None


# --------------------------------------------------------------------------- #
# classify_voicemail
# --------------------------------------------------------------------------- #


def _patch_openai(monkeypatch: pytest.MonkeyPatch, content: str | Exception) -> None:
    client = MagicMock()
    if isinstance(content, Exception):
        client.chat.completions.create = AsyncMock(side_effect=content)
    else:
        choice = MagicMock()
        choice.message.content = content
        completion = MagicMock()
        completion.choices = [choice]
        client.chat.completions.create = AsyncMock(return_value=completion)
    monkeypatch.setattr(
        "app.services.ai.openai_credentials.create_openai_client",
        lambda: client,
    )


async def test_classify_voicemail_normalizes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(
        monkeypatch,
        json.dumps(
            {
                "intent": "book_appointment",
                "urgency": "HIGH",
                "summary": "Caller wants a viewing this week.",
                "callback_requested": True,
            }
        ),
    )
    result = await vm.classify_voicemail("Hi, I'd like to book a viewing.", _make_log())
    assert result.intent == "book_appointment"
    assert result.urgency == "high"
    assert result.callback_requested is True


async def test_classify_voicemail_falls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch, RuntimeError("boom"))
    result = await vm.classify_voicemail("some message", _make_log())
    assert result.urgency == "medium"
    assert result.intent == "other"


async def test_classify_voicemail_empty_transcript_is_fallback() -> None:
    result = await vm.classify_voicemail("   ", _make_log())
    assert result.intent == "other"
    assert result.callback_requested is False


# --------------------------------------------------------------------------- #
# process_voicemail_recording — idempotency + guards
# --------------------------------------------------------------------------- #


async def test_process_skips_when_no_recording_url() -> None:
    result = await vm.process_voicemail_recording("cc-1", None, run_followup=True, log=_make_log())
    assert result is False


async def test_process_is_idempotent_on_duplicate_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vm,
        "claim_redis_idempotency_key",
        AsyncMock(return_value=RedisIdempotencyClaim(key="k", claimed=False, reason="duplicate")),
    )
    # AsyncSessionLocal must not be touched on the duplicate path.
    monkeypatch.setattr(vm, "AsyncSessionLocal", MagicMock(side_effect=AssertionError("no db")))

    result = await vm.process_voicemail_recording(
        "cc-1", "https://x/r.mp3", run_followup=True, log=_make_log()
    )
    assert result is False


async def test_process_returns_false_when_message_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vm,
        "claim_redis_idempotency_key",
        AsyncMock(return_value=RedisIdempotencyClaim(key="k", claimed=True, reason="claimed")),
    )
    db = _make_db(execute_returns=[_Result(scalar=None)])
    _patch_session_local(monkeypatch, db)

    result = await vm.process_voicemail_recording(
        "cc-1", "https://x/r.mp3", run_followup=True, log=_make_log()
    )
    assert result is False


async def test_process_skips_when_transcript_already_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vm,
        "claim_redis_idempotency_key",
        AsyncMock(return_value=RedisIdempotencyClaim(key="k", claimed=True, reason="claimed")),
    )
    message = MagicMock()
    message.transcript = json.dumps({"text": "already done"})
    message.conversation = MagicMock()
    db = _make_db(execute_returns=[_Result(scalar=message)])
    _patch_session_local(monkeypatch, db)

    result = await vm.process_voicemail_recording(
        "cc-1", "https://x/r.mp3", run_followup=True, log=_make_log()
    )
    assert result is False


async def test_process_full_voicemail_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vm,
        "claim_redis_idempotency_key",
        AsyncMock(return_value=RedisIdempotencyClaim(key="k", claimed=True, reason="claimed")),
    )

    message = MagicMock()
    message.id = uuid.uuid4()
    message.transcript = None
    conversation = MagicMock()
    conversation.workspace_id = uuid.uuid4()
    conversation.contact_id = 7
    conversation.contact_phone = "+14155550123"
    message.conversation = conversation

    # session 1: load message; session 2: workspace.get + reload message
    db1 = _make_db(execute_returns=[_Result(scalar=message)])
    db2 = _make_db(execute_returns=[_Result(scalar=message)])
    workspace = MagicMock()
    workspace.id = conversation.workspace_id
    workspace.name = "Acme"
    workspace.settings = {}
    db2.get = AsyncMock(return_value=workspace)
    _patch_session_local(monkeypatch, db1, db2)

    monkeypatch.setattr(vm, "_download_recording", AsyncMock(return_value=b"audio-bytes"))
    monkeypatch.setattr(vm, "transcribe_recording", AsyncMock(return_value="Please call me back"))
    save_transcript = AsyncMock(return_value=True)
    monkeypatch.setattr(vm, "save_call_transcript", save_transcript)
    monkeypatch.setattr(
        vm,
        "classify_voicemail",
        AsyncMock(
            return_value=vm.VoicemailAnalysis(
                intent="callback_request",
                urgency="high",
                summary="Caller wants a callback.",
                callback_requested=True,
            )
        ),
    )
    create_oppo = AsyncMock(return_value=MagicMock())
    notify = AsyncMock(return_value=None)
    automated = AsyncMock(return_value=None)
    monkeypatch.setattr(vm, "_create_followup_opportunity", create_oppo)
    monkeypatch.setattr(vm, "_notify_operators", notify)
    monkeypatch.setattr(vm, "_maybe_automated_response", automated)

    result = await vm.process_voicemail_recording(
        "cc-vm", "https://x/r.mp3", run_followup=True, log=_make_log()
    )

    assert result is True
    save_transcript.assert_awaited_once()
    # transcript persisted as JSON with the voicemail text.
    saved_json = save_transcript.await_args.args[1]
    assert json.loads(saved_json)["text"] == "Please call me back"
    create_oppo.assert_awaited_once()
    notify.assert_awaited_once()
    automated.assert_awaited_once()


async def test_process_recording_without_followup_only_saves_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vm,
        "claim_redis_idempotency_key",
        AsyncMock(return_value=RedisIdempotencyClaim(key="k", claimed=True, reason="claimed")),
    )
    message = MagicMock()
    message.id = uuid.uuid4()
    message.transcript = None
    message.conversation = MagicMock()
    message.conversation.workspace_id = uuid.uuid4()
    message.conversation.contact_id = None
    message.conversation.contact_phone = "+14155550123"
    db1 = _make_db(execute_returns=[_Result(scalar=message)])
    _patch_session_local(monkeypatch, db1)

    monkeypatch.setattr(vm, "_download_recording", AsyncMock(return_value=b"audio"))
    monkeypatch.setattr(vm, "transcribe_recording", AsyncMock(return_value="hello"))
    save_transcript = AsyncMock(return_value=True)
    monkeypatch.setattr(vm, "save_call_transcript", save_transcript)
    classify = AsyncMock()
    monkeypatch.setattr(vm, "classify_voicemail", classify)

    result = await vm.process_voicemail_recording(
        "cc-rec", "https://x/r.mp3", run_followup=False, log=_make_log()
    )

    assert result is True
    save_transcript.assert_awaited_once()
    classify.assert_not_awaited()
