"""GPT-Live voice sessions over the Codex subscription realtime route.

This session type reaches ``gpt-live-1-codex`` through the local Codex CLI
app-server instead of the OpenAI Realtime WebSocket API. The transport is
WebRTC: control events ride the ``oai-events`` data channel and audio rides a
real media track, negotiated with PCMU (G.711 mu-law, 8 kHz) so Telnyx audio
passes through untouched, exactly as the Realtime ``g711_ulaw`` path does.

Differences from :class:`~app.services.ai.voice_agent.VoiceAgentSession` that
the protocol forces:

* ``conversation.item.create`` does not exist in protocol v3. Text turns are
  injected with ``session.context.append``.
* Tool use arrives as ``delegation.created`` rather than function-call events,
  and results are returned via ``delegation.context.append``.
* Transcripts arrive as ``input_transcript.added`` / ``output_transcript.added``
  deltas, and ``turn.done`` may carry partial text, so turns are closed on a
  quiet timer rather than trusting ``turn.done`` to be final.
* Usage is metered locally from ``session.usage.updated`` because the
  subscription voice allowance is not exposed to clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.mediastreams import MediaStreamError

from app.models.agent import Agent
from app.services.ai.call_tracing import ResponseSpans
from app.services.ai.codex_app_server import (
    DEFAULT_CODEX_VOICE,
    SUPPORTED_CODEX_VOICES,
    CodexAppServerBroker,
    CodexAppServerError,
    RealtimeStartOptions,
)
from app.services.ai.live_audio import MuLawRelayTrack, iter_mulaw_frames
from app.services.ai.voice_agent_base import VoiceAgentBase
from app.services.ai.voice_tools import get_tools_from_agent_config

logger = structlog.get_logger()

TOOL_TIMEOUT_SECONDS = 30.0
_EVENT_CHANNEL = "oai-events"
_CONNECT_TIMEOUT_SECONDS = 30.0
# Same-role deltas inside this window belong to one spoken turn (turn.done can
# arrive early with partial text, so it is not trusted to close a turn).
_TURN_QUIET_SECONDS = 3.5

# Instructions handed to the Codex thread agent. In client-managed handoff mode
# the thread is NOT the executor, but the core still routes every delegation
# into it -- without this the thread agent runs real tool work in the
# background and silently drains the subscription's weekly budget.
_THREAD_NOOP_INSTRUCTIONS = (
    "You are not the executor for this session. The client runs every delegated "
    "task. When a delegation arrives, reply with exactly `skip` and call no "
    "tools, read no files, and run no commands."
)

# Voice-side policy. Without it the model delegates fillers and fragments, and
# each one becomes a full agent turn the caller waits through.
_DELEGATION_POLICY = """
## Delegation policy
Delegate only genuine action requests or factual lookups you cannot answer yourself.
Never delegate greetings, acknowledgements, fillers, or half-finished sentences.
Resolve small ambiguities by asking the caller directly instead of delegating.
When you do delegate: give one short acknowledgement, then wait silently.
Read results back in one or two plain spoken sentences. Never read markdown or lists aloud.
""".strip()


class LiveVoiceAgentSession(VoiceAgentBase):
    """GPT-Live session brokered through the Codex subscription.

    Implements the same VoiceAgentProtocol surface as the Realtime session so
    the Telnyx bridge can drive either one, including mu-law passthrough,
    barge-in, transcripts, and tool calls.
    """

    SERVICE_NAME = "live_voice_agent"
    BASE_URL = "codex-app-server://realtime"
    # PCMU is negotiated end to end, so the bridge skips conversion both ways.
    INPUT_AUDIO_FORMAT = "ulaw"
    OUTPUT_AUDIO_FORMAT = "ulaw"

    def __init__(
        self,
        agent: Agent | None = None,
        timezone: str = "America/New_York",
        *,
        broker: CodexAppServerBroker | None = None,
        binary_path: str | None = None,
        cwd: str | None = None,
        thread_model: str | None = None,
        ice_servers: list[str] | None = None,
    ) -> None:
        """Initialize a GPT-Live session.

        Args:
            agent: Agent model supplying prompt, voice, and tool configuration.
            timezone: IANA timezone for date context in prompts.
            broker: Existing app-server broker; one is created when omitted.
            binary_path: Explicit path to the ``codex`` executable.
            cwd: Working directory for the app-server thread.
            thread_model: Codex model for the thread agent. Must be valid for a
                ChatGPT account or delegated turns fail with HTTP 400.
            ice_servers: STUN/TURN URLs for the WebRTC peer connection.
        """
        super().__init__(agent, timezone)
        self._owns_broker = broker is None
        self._broker = broker or CodexAppServerBroker(
            binary_path=binary_path,
            cwd=cwd,
            model=thread_model,
        )
        self._ice_servers = ice_servers or ["stun:stun.l.google.com:19302"]

        self._pc: RTCPeerConnection | None = None
        self._channel: Any = None
        self._outbound_track: MuLawRelayTrack | None = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
        self._remote_reader: asyncio.Task[None] | None = None
        self._thread_id: str | None = None
        self._session_id: str | None = None
        self._connected = asyncio.Event()

        # Tool/delegation plumbing.
        self._tool_callback: Callable[[str, str, dict[str, Any]], Any] | None = None
        self._tool_tasks: set[asyncio.Task[None]] = set()
        self._delegation_lock = asyncio.Lock()

        # Turn bookkeeping (see _TURN_QUIET_SECONDS).
        self._user_turn_buffer = ""
        self._user_turn_deadline = 0.0
        self._turn_flush_task: asyncio.Task[None] | None = None

        # Local metering: the plan-side allowance is not exposed to clients.
        self._audio_duration_ms = 0
        self._response_spans: ResponseSpans | None = None
        self._response_sequence = 0
        self._current_response_id: str | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """True when the data channel is open (overrides the WebSocket check)."""
        return bool(
            self._pc is not None
            and self._channel is not None
            and getattr(self._channel, "readyState", None) == "open"
        )

    async def connect(self) -> bool:
        """Start the app-server, negotiate WebRTC, and open the session."""
        self._response_spans = ResponseSpans("openai-live", "gpt-live")
        try:
            await self._broker.start()
        except CodexAppServerError as exc:
            self.logger.error("codex_app_server_start_failed", error=str(exc))
            return False

        config = RTCConfiguration(iceServers=[RTCIceServer(urls=url) for url in self._ice_servers])
        self._pc = RTCPeerConnection(configuration=config)
        self._outbound_track = MuLawRelayTrack()

        sender = self._pc.addTrack(self._outbound_track)
        _prefer_pcmu(self._pc, sender)

        self._channel = self._pc.createDataChannel(_EVENT_CHANNEL)
        self._channel.on("open", self._on_channel_open)
        self._channel.on("message", self._on_channel_message)
        self._pc.on("track", self._on_track)
        self._pc.on("connectionstatechange", self._on_connection_state_change)

        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)

        try:
            handle = await self._broker.start_realtime(
                self._pc.localDescription.sdp,
                options=self._build_start_options(),
            )
        except CodexAppServerError as exc:
            self.logger.error("codex_realtime_start_failed", error=str(exc))
            await self.disconnect()
            return False

        self._thread_id = handle.thread_id
        self._session_id = handle.session_id
        await self._pc.setRemoteDescription(
            RTCSessionDescription(sdp=handle.answer_sdp, type="answer")
        )

        try:
            await asyncio.wait_for(self._connected.wait(), timeout=_CONNECT_TIMEOUT_SECONDS)
        except TimeoutError:
            self.logger.error("live_voice_channel_open_timeout")
            await self.disconnect()
            return False

        self.logger.info(
            "live_voice_connected",
            thread_id=self._thread_id,
            session_id=self._session_id,
            model="gpt-live-1-codex",
            voice=self._resolved_voice(),
        )
        return True

    def _build_start_options(self) -> RealtimeStartOptions:
        """Build realtime session options from agent configuration."""
        prompt = self._prompt_builder.build_full_prompt(
            include_realism=False,
            include_booking=False,
        )
        tools = get_tools_from_agent_config(
            self.agent,
            enable_booking=bool(self.agent and self.agent.calcom_event_type_id),
            timezone=self._timezone,
        )
        prompt = f"{prompt}\n\n{_DELEGATION_POLICY}"
        if tools:
            prompt = f"{prompt}\n\n{_render_tool_catalog(tools)}"

        return RealtimeStartOptions(
            prompt=prompt,
            realtime_start_instructions=_THREAD_NOOP_INSTRUCTIONS,
            voice=self._resolved_voice(),
            client_managed_handoffs=True,
            delegation_ack_filler=True,
        )

    def _resolved_voice(self) -> str:
        """Map the agent voice onto a Codex realtime voice."""
        configured = (self.agent.voice_id if self.agent else None) or ""
        return configured if configured in SUPPORTED_CODEX_VOICES else DEFAULT_CODEX_VOICE

    async def disconnect(self) -> None:
        """Tear down the realtime session, peer connection, and broker."""
        from app.services.ai.call_tracing import record_provider_cost

        if self._response_spans is not None:
            self._response_spans.close()
            self._response_spans = None
            # This is subscription allowance usage, not a per-call invoice.
            record_provider_cost(None)
        for task in (self._remote_reader, self._turn_flush_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        for task in list(self._tool_tasks):
            task.cancel()
        self._tool_tasks.clear()

        self._flush_user_turn()
        self._save_current_agent_transcript()

        if self._thread_id:
            with contextlib.suppress(CodexAppServerError):
                await self._broker.stop_realtime(self._thread_id)

        if self._outbound_track:
            self._outbound_track.stop()
            self._outbound_track = None

        if self._pc:
            with contextlib.suppress(Exception):
                await self._pc.close()
            self._pc = None

        self._channel = None
        self._connected.clear()
        self._end_audio_stream()

        if self._owns_broker:
            await self._broker.close()

        self.logger.info(
            "live_voice_disconnected",
            audio_duration_ms=self._audio_duration_ms,
            transcript_entries=len(self._transcript_entries),
        )
        self._log_full_transcript()

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Queue caller audio for the model.

        Args:
            audio_data: G.711 mu-law bytes at 8 kHz, straight from Telnyx.
        """
        if self._outbound_track is not None:
            self._outbound_track.push(audio_data)

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        """Yield model audio as mu-law chunks ready for Telnyx."""
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            if self._is_interrupted:
                continue
            yield chunk

    def _on_track(self, track: Any) -> None:
        """Handle the inbound model audio track."""
        if track.kind != "audio":
            return
        self.logger.info("live_voice_track_received", kind=track.kind)
        self._remote_reader = asyncio.create_task(self._pump_remote_audio(track))

    async def _pump_remote_audio(self, track: Any) -> None:
        """Read frames from the model track into the outbound queue."""
        frames = 0
        try:
            while True:
                frame = await track.recv()
                for chunk in iter_mulaw_frames(frame):
                    frames += 1
                    if frames == 1:
                        self.logger.info("live_voice_first_audio_frame", bytes=len(chunk))
                    try:
                        self._audio_queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        # Dropping is correct under back-pressure: stale audio
                        # played late is worse than a gap on a live call.
                        self.logger.warning("live_voice_audio_queue_full")
        except (MediaStreamError, asyncio.CancelledError):
            self.logger.info("live_voice_track_ended", frames=frames)
        except Exception as exc:
            self.logger.exception("live_voice_track_error", error=str(exc))

    # ------------------------------------------------------------------
    # Data channel events
    # ------------------------------------------------------------------

    def _on_channel_open(self) -> None:
        """Mark the session ready once the event channel opens."""
        self._connected.set()
        self.logger.info("live_voice_channel_open")

    def _on_connection_state_change(self) -> None:
        """Log peer connection transitions."""
        state = getattr(self._pc, "connectionState", "unknown")
        self.logger.info("live_voice_connection_state", state=state)
        if state in {"failed", "closed"}:
            self._connected.clear()
            # No more audio is coming. Without this the bridge's receive loop
            # waits on the queue forever instead of ending the call.
            self._end_audio_stream()

    def _end_audio_stream(self) -> None:
        """Signal end-of-audio to :meth:`receive_audio_stream`.

        A full queue must never block teardown, so the stalest chunk is dropped
        to make room for the sentinel.
        """
        try:
            self._audio_queue.put_nowait(None)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._audio_queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._audio_queue.put_nowait(None)

    def _on_channel_message(self, message: Any) -> None:
        """Dispatch a data-channel event."""
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        try:
            event = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            self.logger.warning("live_voice_invalid_event_json")
            return
        if isinstance(event, dict):
            self._handle_event(event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Route a protocol v3 event."""
        self.observe_provider_event(event)
        event_type = event.get("type", "")
        handler = self._EVENT_HANDLERS.get(event_type)
        if handler is None:
            self.logger.debug("live_voice_unhandled_event", event_type=event_type)
            return
        handler(self, event)

    def _handle_session_event(self, event: dict[str, Any]) -> None:
        """Log session lifecycle events."""
        self.logger.info(
            "live_voice_session_event",
            event_type=event.get("type", ""),
            session_id=(event.get("session") or {}).get("id"),
        )

    def _handle_turn_done(self, event: dict[str, Any]) -> None:
        """Close the agent turn only.

        ``turn.done`` can arrive carrying partial text, so the caller's turn is
        closed by the quiet timer instead.
        """
        self._save_current_agent_transcript()
        if self._response_spans is not None and self._current_response_id is not None:
            self._response_spans.finish({"id": self._current_response_id, "status": "completed"})
            self._current_response_id = None

    def _handle_error_event(self, event: dict[str, Any]) -> None:
        """Log a protocol error without tearing down the call."""
        self.logger.error("live_voice_error_event", error=str(event.get("error"))[:500])

    # Protocol v3 event dispatch. Names differ from the Realtime API; see
    # backend/docs/voice/gpt-live-codex.md for the mapping.
    _EVENT_HANDLERS: dict[str, Any] = {
        "session.started": _handle_session_event,
        "session.updated": _handle_session_event,
        "session.usage.updated": lambda self, event: self._record_usage(event),
        "input_transcript.added": lambda self, event: self._handle_user_delta(_event_text(event)),
        "output_transcript.added": lambda self, event: self._append_agent_transcript_delta(
            _event_text(event)
        ),
        "turn.created": lambda self, event: self._start_traced_turn(),
        "turn.done": _handle_turn_done,
        "input_audio.started": lambda self, event: self._handle_speech_started(),
        "delegation.created": lambda self, event: self._handle_delegation(event),
        "error": _handle_error_event,
    }

    def _start_traced_turn(self) -> None:
        self._handle_response_created()
        self._response_sequence += 1
        self._current_response_id = str(self._response_sequence)
        if self._response_spans is not None:
            self._response_spans.start({"id": self._current_response_id})

    def _record_usage(self, event: dict[str, Any]) -> None:
        """Track local audio usage against the subscription allowance."""
        usage = event.get("usage") or {}
        duration = usage.get("audio_duration_ms")
        if isinstance(duration, int):
            self._audio_duration_ms = duration
        limit = event.get("usage_limit") or {}
        self.logger.info(
            "live_voice_usage",
            audio_duration_ms=self._audio_duration_ms,
            limit_status=limit.get("status"),
            reset_seconds=limit.get("reset_seconds"),
        )

    # ------------------------------------------------------------------
    # Turn bookkeeping
    # ------------------------------------------------------------------

    def _handle_user_delta(self, text: str) -> None:
        """Accumulate caller transcript deltas into one logical turn."""
        if not text:
            return
        self._user_turn_buffer += text
        self._user_turn_deadline = time.monotonic() + _TURN_QUIET_SECONDS
        if self._turn_flush_task is not None and not self._turn_flush_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop: the turn is still committed on disconnect.
            self.logger.debug("live_voice_turn_timer_no_loop")
            return
        self._turn_flush_task = loop.create_task(self._flush_user_turn_when_quiet())

    async def _flush_user_turn_when_quiet(self) -> None:
        """Close the caller's turn once deltas stop arriving.

        Cancellation propagates: :meth:`disconnect` commits the buffered turn
        itself, so there is nothing to salvage here.
        """
        while True:
            remaining = self._user_turn_deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)
        self._flush_user_turn()

    def _flush_user_turn(self) -> None:
        """Commit the buffered caller turn to the transcript."""
        if self._user_turn_buffer.strip():
            self._add_user_transcript(self._user_turn_buffer.strip())
        self._user_turn_buffer = ""

    # ------------------------------------------------------------------
    # Delegation (tool calling)
    # ------------------------------------------------------------------

    def set_tool_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], Any],
    ) -> None:
        """Register the executor for delegated tasks."""
        self._tool_callback = callback

    def _handle_delegation(self, event: dict[str, Any]) -> None:
        """Run a delegated task and feed the result back to the model."""
        item = event.get("item") or {}
        item_id = item.get("id")
        if not item_id:
            self.logger.warning("live_voice_delegation_missing_id")
            return

        request_text = _item_text(item) or self._user_transcript
        if not request_text.strip():
            self.logger.info("live_voice_delegation_skipped_empty", item_id=item_id)
            return

        self.logger.info(
            "live_voice_delegation_created",
            item_id=item_id,
            target=item.get("target"),
            request_preview=request_text[:120],
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - defensive
            self.logger.error("live_voice_delegation_no_loop", item_id=item_id)
            return
        task = loop.create_task(self._run_delegation(item_id, request_text))
        self._tool_tasks.add(task)
        task.add_done_callback(self._tool_tasks.discard)

    async def _run_delegation(self, item_id: str, request_text: str) -> None:
        """Execute one delegation, serialized against other delegations."""
        # One task at a time: concurrent agent turns make the caller wait
        # through overlapping results.
        async with self._delegation_lock:
            if self._tool_callback is None:
                await self._submit_delegation_result(
                    item_id, "That is not something I can do on this call."
                )
                return
            try:
                result = await asyncio.wait_for(
                    self._tool_callback(item_id, "delegation", {"request": request_text}),
                    timeout=TOOL_TIMEOUT_SECONDS,
                )
                await self._submit_delegation_result(item_id, _render_result(result))
            except TimeoutError:
                self.logger.warning("live_voice_delegation_timeout", item_id=item_id)
                await self._submit_delegation_result(
                    item_id, "That took too long. Tell the caller you will follow up."
                )
            except Exception as exc:
                self.logger.exception("live_voice_delegation_error", error=str(exc))
                await self._submit_delegation_result(
                    item_id, "That failed. Apologise briefly and continue the conversation."
                )

    async def _submit_delegation_result(self, item_id: str, text: str) -> None:
        """Return a delegation result over the working result channel."""
        self._send_client_event(
            {
                "type": "delegation.context.append",
                "delegation_item_id": item_id,
                "content": [{"type": "input_text", "text": text}],
            }
        )

    async def submit_tool_result(self, call_id: str, result: dict[str, Any]) -> None:
        """Submit a tool result (ToolCallableProtocol compatibility)."""
        await self._submit_delegation_result(call_id, _render_result(result))

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def _send_client_event(self, event: dict[str, Any]) -> None:
        """Send a client event on the data channel."""
        if not self.is_connected():
            self.logger.warning("live_voice_send_skipped_not_connected", event=event.get("type"))
            return
        try:
            self._channel.send(json.dumps(event))
        except Exception as exc:
            self.logger.exception("live_voice_send_failed", error=str(exc))

    def _append_text_turn(self, text: str) -> None:
        """Make the model speak in response to injected text.

        Protocol v3 has no ``conversation.item.create``; appending input text to
        the session context is what triggers a spoken turn.
        """
        self._send_client_event(
            {
                "type": "session.context.append",
                "content": [{"type": "input_text", "text": text}],
            }
        )

    async def configure_session(
        self,
        voice: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        turn_detection_mode: str | None = None,
        turn_detection_threshold: float | None = None,
        silence_duration_ms: int | None = None,
    ) -> None:
        """Update session instructions and voice mid-call.

        Turn detection and temperature are not client-configurable on the
        full-duplex route; the model owns turn-taking.
        """
        del temperature, turn_detection_mode, turn_detection_threshold, silence_duration_ms

        session: dict[str, Any] = {}
        if system_prompt:
            rebuilt = self._prompt_builder.build_full_prompt(
                base_prompt=system_prompt,
                include_realism=False,
                include_booking=False,
            )
            session["prompt"] = f"{rebuilt}\n\n{_DELEGATION_POLICY}"
        if voice and voice in SUPPORTED_CODEX_VOICES:
            session["voice"] = voice
        if not session:
            return

        self._send_client_event({"type": "session.update", "session": session})
        self.logger.info("live_voice_session_reconfigured", updates=sorted(session))

    async def trigger_initial_response(
        self,
        greeting: str | None = None,
        is_outbound: bool = False,
    ) -> None:
        """Have the model open the conversation."""
        if is_outbound:
            prompt_text = self._prompt_builder.get_outbound_opener_prompt()
        else:
            message = greeting or self._pending_greeting
            if not message and self.agent and self.agent.initial_greeting:
                message = self.agent.initial_greeting
            prompt_text = self._prompt_builder.get_inbound_greeting_prompt(message)

        self._append_text_turn(prompt_text)
        self.logger.info("live_voice_initial_response_triggered", is_outbound=is_outbound)

    async def send_greeting(self, greeting: str) -> None:
        """Store a greeting for :meth:`trigger_initial_response`."""
        self._pending_greeting = greeting

    async def inject_context(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
        is_outbound: bool = False,
    ) -> None:
        """Inject contact/offer context into the running session."""
        self._call_context = {
            "contact": contact_info,
            "offer": offer_info,
            "is_outbound": is_outbound,
        }
        if not contact_info and not offer_info:
            return

        # Mirrors the Realtime path: rebuild the whole prompt with context
        # folded in, since v3 has no conversation-item injection.
        full_instructions = self._prompt_builder.build_full_prompt(
            include_realism=False,
            include_booking=False,
            contact_info=contact_info,
            offer_info=offer_info,
            is_outbound=is_outbound,
        )
        self._send_client_event(
            {
                "type": "session.update",
                "session": {"prompt": f"{full_instructions}\n\n{_DELEGATION_POLICY}"},
            }
        )
        self.logger.info(
            "live_voice_context_injected",
            has_contact=bool(contact_info),
            has_offer=bool(offer_info),
        )

    async def cancel_response(self) -> None:
        """Stop current playback on barge-in.

        The model handles interruption itself on a full-duplex route; this
        drains locally buffered audio so the caller stops hearing it at once.
        """
        self._handle_speech_started()
        drained = 0
        while not self._audio_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._audio_queue.get_nowait()
                drained += 1
        self._send_client_event({"type": "output_audio.playback.play", "playing": False})
        self.logger.info("live_voice_response_cancelled", drained_chunks=drained)


def _prefer_pcmu(pc: RTCPeerConnection, sender: RTCRtpSender) -> None:
    """Rank PCMU first so Telnyx mu-law normally needs no transcoding."""
    codecs = list(RTCRtpSender.getCapabilities("audio").codecs)
    pcmu = [c for c in codecs if c.mimeType.lower() == "audio/pcmu"]
    if not pcmu:
        logger.warning("live_voice_pcmu_unavailable")
        return

    # Rank PCMU first but keep the rest: restricting to one codec would fail
    # negotiation outright, and iter_mulaw_frames converts any fallback.
    others = [c for c in codecs if c.mimeType.lower() != "audio/pcmu"]
    for transceiver in pc.getTransceivers():
        if transceiver.sender is sender:
            transceiver.setCodecPreferences(pcmu + others)
            return


def _event_text(event: dict[str, Any]) -> str:
    """Extract delta text from a transcript event."""
    for key in ("delta", "text"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return _item_text(event.get("item") or {})


def _item_text(item: dict[str, Any]) -> str:
    """Extract concatenated text from an item's content array."""
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        part.get("text", "")
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    return "".join(parts)


def _render_result(result: Any) -> str:
    """Render a tool result as short text the model can speak from."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if result.get("success") is False:
            return f"That did not work: {result.get('error', 'unknown error')}"
        for key in ("message", "summary", "result", "text"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    return json.dumps(result, default=str)[:2000]


def _render_tool_catalog(tools: list[dict[str, Any]]) -> str:
    """Describe available actions in prose.

    The realtime route has no client-side tool schema, so capabilities are
    conveyed in the prompt and executed through delegation.
    """
    lines = ["## Actions you can request", "Delegate these to your assistant when needed:"]
    for tool in tools:
        name = tool.get("name") or (tool.get("function") or {}).get("name")
        description = tool.get("description") or (tool.get("function") or {}).get("description")
        if name:
            lines.append(f"- {name}: {description or 'no description'}")
    return "\n".join(lines)
