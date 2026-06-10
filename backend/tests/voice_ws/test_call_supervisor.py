"""Tests for live-call supervision: registry + supervisor control socket.

Covers:
- :class:`LiveCallRegistry` presence, workspace scoping, and subscriber fan-out.
- :class:`LiveCall` operator controls (whisper / barge / unbarge / barge audio).
- The supervisor WebSocket auth gate and per-message control dispatch.

No real network or database: the Telnyx socket and provider session are fakes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status

from app.services.calls.live_call_registry import (
    LiveCall,
    LiveCallRegistry,
)
from app.websockets import call_supervisor as cs

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _make_telnyx_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


def _make_voice_session(*, supports_whisper: bool = True) -> MagicMock:
    session = MagicMock()
    session.cancel_response = AsyncMock()
    if supports_whisper:
        session.inject_operator_guidance = AsyncMock()
    else:
        # Simulate a provider session without guidance support.
        del session.inject_operator_guidance
    return session


def _make_live_call(
    *,
    call_id: str = "call-1",
    workspace_id: str = "ws-1",
    session: MagicMock | None = None,
) -> LiveCall:
    return LiveCall(
        call_id=call_id,
        workspace_id=workspace_id,
        telnyx_ws=_make_telnyx_ws(),
        voice_session=session or _make_voice_session(),
        direction="inbound",
        agent_name="Aria",
        contact_name="John Doe",
        contact_phone="+15551234567",
    )


def _make_supervisor_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.scope = {}
    return ws


# ---------------------------------------------------------------------------
# Registry: presence + workspace scoping
# ---------------------------------------------------------------------------


class TestRegistryScoping:
    def test_register_and_get_in_same_workspace(self) -> None:
        registry = LiveCallRegistry()
        call = _make_live_call(workspace_id="ws-1")
        registry.register(call)
        assert registry.get("call-1", workspace_id="ws-1") is call

    def test_get_cross_workspace_returns_none(self) -> None:
        registry = LiveCallRegistry()
        registry.register(_make_live_call(workspace_id="ws-1"))
        # An operator in ws-2 must not be able to resolve a ws-1 call.
        assert registry.get("call-1", workspace_id="ws-2") is None

    def test_get_unknown_call_returns_none(self) -> None:
        registry = LiveCallRegistry()
        assert registry.get("missing") is None

    def test_unregister_is_idempotent(self) -> None:
        registry = LiveCallRegistry()
        registry.register(_make_live_call())
        registry.unregister("call-1")
        registry.unregister("call-1")  # no raise
        assert registry.get("call-1") is None

    def test_list_for_workspace_filters_by_tenant(self) -> None:
        registry = LiveCallRegistry()
        registry.register(_make_live_call(call_id="a", workspace_id="ws-1"))
        registry.register(_make_live_call(call_id="b", workspace_id="ws-1"))
        registry.register(_make_live_call(call_id="c", workspace_id="ws-2"))
        ws1 = registry.list_for_workspace("ws-1")
        assert {info.call_id for info in ws1} == {"a", "b"}

    def test_info_snapshot_serializes(self) -> None:
        call = _make_live_call()
        data = call.info().as_dict()
        assert data["call_id"] == "call-1"
        assert data["direction"] == "inbound"
        assert data["contact_name"] == "John Doe"
        assert data["supervisor_count"] == 0
        assert data["barged"] is False
        assert isinstance(data["duration_seconds"], int)


# ---------------------------------------------------------------------------
# Audio fan-out
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_publish_delivers_to_subscriber(self) -> None:
        call = _make_live_call()
        queue = call.add_subscriber()
        assert queue is not None
        call.publish("caller", b"\xff" * 160)
        item = queue.get_nowait()
        assert item == {"track": "caller", "mulaw": b"\xff" * 160}

    def test_remove_subscriber_stops_delivery(self) -> None:
        call = _make_live_call()
        queue = call.add_subscriber()
        assert queue is not None
        call.remove_subscriber(queue)
        call.publish("agent", b"\x01" * 160)
        assert queue.empty()

    def test_subscriber_cap_enforced(self) -> None:
        call = _make_live_call()
        queues = [call.add_subscriber() for _ in range(5)]
        assert all(q is not None for q in queues)
        # 6th subscriber is rejected.
        assert call.add_subscriber() is None

    def test_publish_drops_oldest_when_queue_full(self) -> None:
        call = _make_live_call()
        queue = call.add_subscriber()
        assert queue is not None
        # Fill beyond capacity; publish must never raise or block.
        for i in range(queue.maxsize + 50):
            call.publish("caller", bytes([i % 256]) * 4)
        assert queue.qsize() == queue.maxsize

    def test_publish_noop_without_subscribers(self) -> None:
        call = _make_live_call()
        call.publish("caller", b"\xff" * 160)  # no raise


# ---------------------------------------------------------------------------
# Operator controls
# ---------------------------------------------------------------------------


class TestOperatorControls:
    async def test_whisper_delegates_to_session(self) -> None:
        session = _make_voice_session()
        call = _make_live_call(session=session)
        assert await call.whisper("Offer the discount") is True
        session.inject_operator_guidance.assert_awaited_once_with("Offer the discount")

    async def test_whisper_empty_text_is_noop(self) -> None:
        session = _make_voice_session()
        call = _make_live_call(session=session)
        assert await call.whisper("   ") is False
        session.inject_operator_guidance.assert_not_called()

    async def test_whisper_unsupported_provider_returns_false(self) -> None:
        session = _make_voice_session(supports_whisper=False)
        call = _make_live_call(session=session)
        assert await call.whisper("hi") is False

    async def test_start_barge_mutes_ai_and_cancels_response(self) -> None:
        session = _make_voice_session()
        call = _make_live_call(session=session)
        await call.start_barge(operator_user_id=42)
        assert call.ai_muted is True
        assert call.barged_by == 42
        session.cancel_response.assert_awaited_once()

    async def test_stop_barge_unmutes(self) -> None:
        call = _make_live_call()
        await call.start_barge(1)
        await call.stop_barge()
        assert call.ai_muted is False
        assert call.barged_by is None

    async def test_barge_audio_noop_when_not_barged(self) -> None:
        call = _make_live_call()
        await call.send_barge_audio_pcm16(b"\x00\x00" * 320)
        call._telnyx_ws.send_text.assert_not_awaited()

    async def test_barge_audio_written_to_telnyx_when_barged(self) -> None:
        call = _make_live_call()
        await call.start_barge(1)
        # 320 PCM16 samples @16k -> resample 8k -> µ-law, then base64 framed.
        await call.send_barge_audio_pcm16(b"\x00\x00" * 320)
        call._telnyx_ws.send_text.assert_awaited_once()
        msg = json.loads(call._telnyx_ws.send_text.await_args.args[0])
        assert msg["event"] == "media"
        assert base64.b64decode(msg["media"]["payload"])

    async def test_send_to_telnyx_serializes_and_frames(self) -> None:
        call = _make_live_call()
        await call.send_to_telnyx_mulaw(b"\xab" * 160)
        msg = json.loads(call._telnyx_ws.send_text.await_args.args[0])
        assert base64.b64decode(msg["media"]["payload"]) == b"\xab" * 160


# ---------------------------------------------------------------------------
# Supervisor control-message dispatch
# ---------------------------------------------------------------------------


class TestControlMessageDispatch:
    async def test_monitor_adds_subscriber_and_starts_pump(self) -> None:
        call = _make_live_call()
        ws = _make_supervisor_ws()
        log = MagicMock()

        monitoring, task = await cs._handle_control_message(
            ws, call, {"type": "monitor"}, operator_user_id=1, monitoring=False, log=log
        )
        try:
            assert monitoring is True
            assert task is not None
            assert call.supervisor_count == 1
            ws.send_json.assert_awaited_with({"type": "monitoring"})
        finally:
            if task is not None:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    async def test_monitor_twice_does_not_double_subscribe(self) -> None:
        call = _make_live_call()
        ws = _make_supervisor_ws()
        log = MagicMock()
        monitoring, task = await cs._handle_control_message(
            ws, call, {"type": "monitor"}, operator_user_id=1, monitoring=False, log=log
        )
        try:
            monitoring, task2 = await cs._handle_control_message(
                ws, call, {"type": "monitor"}, operator_user_id=1, monitoring=monitoring, log=log
            )
            assert task2 is None
            assert call.supervisor_count == 1
        finally:
            if task is not None:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    async def test_whisper_message_invokes_guidance(self) -> None:
        session = _make_voice_session()
        call = _make_live_call(session=session)
        ws = _make_supervisor_ws()
        await cs._handle_control_message(
            ws,
            call,
            {"type": "whisper", "text": "ask about budget"},
            operator_user_id=1,
            monitoring=True,
            log=MagicMock(),
        )
        session.inject_operator_guidance.assert_awaited_once_with("ask about budget")
        ws.send_json.assert_awaited_with({"type": "whispered"})

    async def test_barge_then_unbarge(self) -> None:
        call = _make_live_call()
        ws = _make_supervisor_ws()
        log = MagicMock()
        await cs._handle_control_message(
            ws, call, {"type": "barge"}, operator_user_id=7, monitoring=True, log=log
        )
        assert call.ai_muted is True
        ws.send_json.assert_awaited_with({"type": "barge_started"})

        await cs._handle_control_message(
            ws, call, {"type": "unbarge"}, operator_user_id=7, monitoring=True, log=log
        )
        assert call.ai_muted is False
        ws.send_json.assert_awaited_with({"type": "barge_stopped"})

    async def test_barge_audio_forwarded_when_barged(self) -> None:
        call = _make_live_call()
        await call.start_barge(1)
        ws = _make_supervisor_ws()
        payload = base64.b64encode(b"\x00\x00" * 320).decode()
        await cs._handle_control_message(
            ws,
            call,
            {"type": "barge_audio", "data": payload},
            operator_user_id=1,
            monitoring=True,
            log=MagicMock(),
        )
        call._telnyx_ws.send_text.assert_awaited_once()

    async def test_unknown_message_returns_error(self) -> None:
        call = _make_live_call()
        ws = _make_supervisor_ws()
        await cs._handle_control_message(
            ws, call, {"type": "frobnicate"}, operator_user_id=1, monitoring=True, log=MagicMock()
        )
        sent = ws.send_json.await_args.args[0]
        assert sent["type"] == "error"

    async def test_monitor_rejected_when_call_full(self) -> None:
        call = _make_live_call()
        for _ in range(5):
            call.add_subscriber()
        ws = _make_supervisor_ws()
        monitoring, task = await cs._handle_control_message(
            ws, call, {"type": "monitor"}, operator_user_id=1, monitoring=False, log=MagicMock()
        )
        assert monitoring is False
        assert task is None
        sent = ws.send_json.await_args.args[0]
        assert sent["type"] == "error"


# ---------------------------------------------------------------------------
# Endpoint auth gate
# ---------------------------------------------------------------------------


class TestEndpointAuth:
    async def test_missing_token_rejected_before_accept(self) -> None:
        ws = MagicMock()
        ws.query_params = {}
        ws.cookies = {}
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_json = AsyncMock()

        await cs.call_supervisor_endpoint(ws, str(uuid.uuid4()), "call-1")

        # Auth fails -> socket closed with policy violation, never accepted.
        ws.accept.assert_not_called()
        ws.close.assert_awaited()
        codes = [c.kwargs.get("code") for c in ws.close.await_args_list]
        assert status.WS_1008_POLICY_VIOLATION in codes

    async def test_authenticated_but_call_not_active_rejected(self, monkeypatch: Any) -> None:
        ws = MagicMock()
        ws.query_params = {"token": "t"}
        ws.cookies = {}
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_json = AsyncMock()

        async def _auth_ok(_ws: Any, _workspace: str, _log: Any) -> bool:
            return True

        monkeypatch.setattr(cs, "_authenticate_websocket", _auth_ok)

        # Registry has no such call -> "Call not active".
        await cs.call_supervisor_endpoint(ws, str(uuid.uuid4()), "no-such-call")

        ws.accept.assert_awaited()
        sent = ws.send_json.await_args_list[0].args[0]
        assert sent == {"type": "error", "message": "Call not active"}
        codes = [c.kwargs.get("code") for c in ws.close.await_args_list]
        assert status.WS_1008_POLICY_VIOLATION in codes
