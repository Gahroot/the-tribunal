"""Operator-side live call supervision WebSocket.

Lets an authenticated workspace operator attach to a live Telnyx<->AI call and:

- **listen**: stream the call's audio (caller + AI), transcoded to PCM16 24kHz
  for the browser, exactly like the voice-test endpoint;
- **whisper**: inject private guidance into the AI session that steers its next
  response without the caller hearing it;
- **barge**: take over the call \u2014 mute the AI and speak to the caller directly
  via the operator's microphone, then hand control back.

Auth mirrors ``voice_test``: a short-lived ``/auth/ws-ticket`` JWT (or the
same-origin access cookie) is validated and the user's workspace membership is
checked *before* the socket is accepted. The target call is then resolved from
the in-process :class:`LiveCallRegistry`, scoped to the operator's workspace so
one tenant can never supervise another tenant's call.

Protocol
--------
Client -> Server (JSON):
    {"type": "monitor"}                      start receiving audio
    {"type": "whisper", "text": "..."}       inject AI guidance
    {"type": "barge"}                        take over (mute AI)
    {"type": "barge_audio", "data": "<b64 pcm16 16k>"}  operator mic audio
    {"type": "unbarge"}                      hand control back to AI
    {"type": "pong"}                         heartbeat reply

Server -> Client (JSON):
    {"type": "attached", "call": {...}}      roster snapshot for the call
    {"type": "audio", "track": "caller"|"agent", "data": "<b64 pcm16 24k>"}
    {"type": "barge_started"} / {"type": "barge_stopped"}
    {"type": "whispered"}
    {"type": "error", "message": "..."}
    {"type": "call_ended"}
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any

try:  # Python 3.13 removed stdlib ``audioop``.
    import audioop
except ModuleNotFoundError:  # pragma: no cover
    import audioop_lts as audioop  # type: ignore[no-redef]

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.services.calls.live_call_registry import LiveCall, get_live_call_registry
from app.websockets.connection_limits import (
    HeartbeatMonitor,
    enforce_duration_cap,
)
from app.websockets.voice_test import _authenticate_websocket

router = APIRouter()
logger = structlog.get_logger()


def _mulaw_to_pcm16_24k(mulaw: bytes) -> bytes:
    """Decode Telnyx µ-law 8kHz to PCM16 24kHz for browser playback."""
    pcm_8k = audioop.ulaw2lin(mulaw, 2)
    pcm_24k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 24000, None)
    return pcm_24k


async def _resolve_operator_user_id(websocket: WebSocket) -> int | None:
    """Best-effort extraction of the operator's user id from the ws ticket.

    Used only to attribute a barge-in in logs/roster. Auth itself is already
    enforced by ``_authenticate_websocket`` before this is called.
    """
    from app.core.security import decode_access_token

    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None


async def _pump_audio_to_operator(
    websocket: WebSocket,
    queue: asyncio.Queue[dict[str, Any]],
    log: Any,
) -> None:
    """Drain the call's fan-out queue and forward transcoded audio frames."""
    try:
        while True:
            frame = await queue.get()
            pcm24 = _mulaw_to_pcm16_24k(frame["mulaw"])
            await websocket.send_json(
                {
                    "type": "audio",
                    "track": frame["track"],
                    "data": base64.b64encode(pcm24).decode("utf-8"),
                }
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # socket closed / transcode error
        log.info("supervisor_audio_pump_stopped", error=str(exc))


async def _handle_control_message(  # noqa: PLR0911
    websocket: WebSocket,
    live_call: LiveCall,
    message: dict[str, Any],
    *,
    operator_user_id: int | None,
    monitoring: bool,
    log: Any,
) -> tuple[bool, asyncio.Task[None] | None]:
    """Apply one operator control message.

    Returns ``(monitoring, audio_task)`` where ``audio_task`` is set only when a
    ``monitor`` message just started the audio pump.
    """
    msg_type = message.get("type", "")
    audio_task: asyncio.Task[None] | None = None

    if msg_type == "monitor":
        if not monitoring:
            queue = live_call.add_subscriber()
            if queue is None:
                await websocket.send_json(
                    {"type": "error", "message": "Too many supervisors on this call"}
                )
            else:
                audio_task = asyncio.create_task(
                    _pump_audio_to_operator(websocket, queue, log),
                    name="supervisor-audio-pump",
                )
                websocket.scope["supervisor_queue"] = queue
                monitoring = True
                await websocket.send_json({"type": "monitoring"})
        return monitoring, audio_task

    if msg_type == "whisper":
        ok = await live_call.whisper(str(message.get("text", "")))
        await websocket.send_json(
            {"type": "whispered"} if ok else {"type": "error", "message": "Whisper failed"}
        )
        return monitoring, audio_task

    if msg_type == "barge":
        await live_call.start_barge(operator_user_id or 0)
        await websocket.send_json({"type": "barge_started"})
        return monitoring, audio_task

    if msg_type == "barge_audio":
        data = message.get("data", "")
        if data:
            with contextlib.suppress(Exception):
                await live_call.send_barge_audio_pcm16(base64.b64decode(data))
        return monitoring, audio_task

    if msg_type == "unbarge":
        await live_call.stop_barge()
        await websocket.send_json({"type": "barge_stopped"})
        return monitoring, audio_task

    if msg_type == "pong":
        return monitoring, audio_task

    await websocket.send_json({"type": "error", "message": f"Unknown message: {msg_type}"})
    return monitoring, audio_task


async def _supervise(
    websocket: WebSocket,
    live_call: LiveCall,
    *,
    operator_user_id: int | None,
    heartbeat: HeartbeatMonitor,
    log: Any,
) -> None:
    """Run the operator control loop until disconnect."""
    monitoring = False
    audio_task: asyncio.Task[None] | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            heartbeat.mark_activity()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            monitoring, new_task = await _handle_control_message(
                websocket,
                live_call,
                message,
                operator_user_id=operator_user_id,
                monitoring=monitoring,
                log=log,
            )
            if new_task is not None:
                audio_task = new_task
    except WebSocketDisconnect:
        log.info("supervisor_disconnected")
    finally:
        if audio_task is not None:
            audio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await audio_task
        queue = websocket.scope.get("supervisor_queue")
        if queue is not None:
            live_call.remove_subscriber(queue)
        # Releasing the operator must not leave the AI muted if they bargeed in
        # and then dropped — hand control back so the call keeps working.
        with contextlib.suppress(Exception):
            await live_call.stop_barge()


@router.websocket("/voice/supervise/{workspace_id}/{call_id}")
async def call_supervisor_endpoint(
    websocket: WebSocket,
    workspace_id: str,
    call_id: str,
) -> None:
    """Operator live-call supervision socket (listen / whisper / barge).

    Args:
        websocket: WebSocket from the operator's browser.
        workspace_id: Workspace UUID the operator belongs to.
        call_id: Telnyx call-control id of the live call to supervise.
    """
    log = logger.bind(
        endpoint="call_supervisor",
        workspace_id=workspace_id,
        call_id=call_id,
    )
    log.info("call_supervisor_connection_received")

    # Authenticate + authorize BEFORE accepting (mirrors voice_test).
    if not await _authenticate_websocket(websocket, workspace_id, log):
        return

    # Resolve the target call, scoped to this workspace. Cross-tenant lookups
    # return None and are rejected as "not found".
    live_call = get_live_call_registry().get(call_id, workspace_id=workspace_id)
    if live_call is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Call not active"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    operator_user_id = await _resolve_operator_user_id(websocket)

    await websocket.accept()
    await websocket.send_json({"type": "attached", "call": live_call.info().as_dict()})

    heartbeat = HeartbeatMonitor(websocket, log)
    heartbeat.start()
    duration_task = asyncio.create_task(
        enforce_duration_cap(
            websocket,
            log,
            max_seconds=settings.voice_max_call_duration_seconds,
        ),
        name="call-supervisor-duration-cap",
    )
    try:
        await _supervise(
            websocket,
            live_call,
            operator_user_id=operator_user_id,
            heartbeat=heartbeat,
            log=log,
        )
    except Exception as exc:
        log.exception("call_supervisor_error", error=str(exc))
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        await heartbeat.stop()
        duration_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await duration_task
        with contextlib.suppress(Exception):
            await websocket.close()
        log.info("call_supervisor_session_ended")
