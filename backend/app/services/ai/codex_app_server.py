"""Broker for the Codex CLI ``app-server`` realtime route.

The Codex CLI (>= 0.154) exposes a realtime conversation mode backed by the
signed-in ChatGPT/Codex subscription rather than an OpenAI API key. A local
broker spawns ``codex app-server`` (newline-delimited JSON-RPC over stdio),
opens a thread, and starts a realtime session by exchanging a WebRTC SDP
offer for an answer. Media then flows peer-to-peer between our process and
the ChatGPT backend; this broker only performs signalling.

Credentials never pass through this module: ``codex app-server`` reads the
local ``codex login`` state (``~/.codex/auth.json``). ``OPENAI_API_KEY`` and
``CODEX_API_KEY`` are deliberately stripped from the child environment so the
subscription lane is used instead of a metered API key.

Protocol version ``v3`` maps to the ``gpt-live-1-codex`` model. See
``docs/voice/gpt-live-codex.md`` for the full event table.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Protocol version -> model, per the Codex realtime route.
REALTIME_PROTOCOL_VERSION = "v3"
REALTIME_MODEL = "gpt-live-1-codex"

# Voices accepted by the v1/v3 realtime route.
SUPPORTED_CODEX_VOICES = frozenset(
    {"cove", "juniper", "maple", "spruce", "ember", "vale", "breeze", "arbor", "sol"}
)
DEFAULT_CODEX_VOICE = "cove"

# Environment variables that would silently switch the child off the
# subscription lane and onto metered API billing.
_STRIPPED_CHILD_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")

# Extra locations to search when PATH is minimal (systemd, Docker, Railway).
_BINARY_CANDIDATES = (
    "~/.npm-global/bin/codex",
    "~/.local/bin/codex",
    "~/.cargo/bin/codex",
    "/opt/homebrew/bin/codex",
    "/usr/local/bin/codex",
)

_STARTUP_TIMEOUT_SECONDS = 30.0
_REQUEST_TIMEOUT_SECONDS = 30.0
_SDP_TIMEOUT_SECONDS = 30.0
_SHUTDOWN_TIMEOUT_SECONDS = 5.0
# stdio line cap. Realtime SDP payloads far exceed asyncio's 64 KiB default,
# but an unbounded buffer would let a wedged child exhaust memory.
_MAX_LINE_BYTES = 8 * 1024 * 1024


class CodexAppServerError(RuntimeError):
    """Raised when the Codex app-server cannot be started or driven."""


class CodexAuthError(CodexAppServerError):
    """Raised when the app-server has no usable ChatGPT subscription login."""


@dataclass(slots=True)
class RealtimeSessionHandle:
    """Identifiers and SDP answer for a started realtime session."""

    thread_id: str
    answer_sdp: str
    session_id: str | None = None


@dataclass(slots=True)
class RealtimeStartOptions:
    """Session parameters for ``thread/realtime/start``."""

    prompt: str
    realtime_start_instructions: str | None = None
    voice: str = DEFAULT_CODEX_VOICE
    output_modality: str = "audio"
    version: str = REALTIME_PROTOCOL_VERSION
    client_managed_handoffs: bool = True
    delegation_ack_filler: bool = True

    def to_params(self, thread_id: str, offer_sdp: str) -> dict[str, Any]:
        """Render JSON-RPC params for ``thread/realtime/start``."""
        voice = self.voice if self.voice in SUPPORTED_CODEX_VOICES else DEFAULT_CODEX_VOICE
        params: dict[str, Any] = {
            "threadId": thread_id,
            "transport": {"type": "webrtc", "sdp": offer_sdp},
            "outputModality": self.output_modality,
            "version": self.version,
            "voice": voice,
            "prompt": self.prompt,
            "clientManagedHandoffs": self.client_managed_handoffs,
            "delegationAckFiller": self.delegation_ack_filler,
        }
        if self.realtime_start_instructions:
            params["realtimeStartInstructions"] = self.realtime_start_instructions
        return params


def resolve_codex_binary(explicit_path: str | None = None) -> str:
    """Locate the ``codex`` executable.

    Args:
        explicit_path: Configured absolute path, checked first.

    Returns:
        Absolute path to the codex binary.

    Raises:
        CodexAppServerError: If no executable is found.
    """
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise CodexAppServerError(f"Configured codex binary is not executable: {explicit_path}")

    found = shutil.which("codex")
    if found:
        return found

    for raw in _BINARY_CANDIDATES:
        candidate = Path(raw).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise CodexAppServerError(
        "codex CLI not found. Install it (npm i -g @openai/codex) and run `codex login`."
    )


def build_child_env(binary_path: str) -> dict[str, str]:
    """Build the child environment for ``codex app-server``.

    Strips API-key variables so the child authenticates with the local
    subscription login, and ensures the binary's directory is on PATH.
    """
    env = dict(os.environ)
    for key in _STRIPPED_CHILD_ENV:
        env.pop(key, None)

    bin_dir = str(Path(binary_path).parent)
    path_parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    if bin_dir not in path_parts:
        path_parts.insert(0, bin_dir)
    env["PATH"] = os.pathsep.join(path_parts)
    return env


class CodexAppServerBroker:
    """Manages a ``codex app-server`` child process and its realtime sessions.

    One broker owns one child process and drives JSON-RPC over its stdio.
    Instances are not safe to share across event loops.
    """

    def __init__(
        self,
        *,
        binary_path: str | None = None,
        cwd: str | None = None,
        model_provider: str = "openai",
        model: str | None = None,
    ) -> None:
        self._binary_path = binary_path
        self._cwd = cwd
        self._model_provider = model_provider
        self._model = model
        self.logger = logger.bind(service="codex_app_server")

        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notifications: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._closed = False
        self._thread_id: str | None = None
        self._stderr_tail: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True when the child process is alive."""
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Spawn the app-server and complete the JSON-RPC handshake."""
        if self.is_running:
            return

        binary = resolve_codex_binary(self._binary_path)
        args = [
            binary,
            "app-server",
            "--listen",
            "stdio://",
            "--enable",
            "realtime_conversation",
            "-c",
            f"model_provider={self._model_provider}",
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_child_env(binary),
                cwd=self._cwd,
                # Realtime payloads (notably SDP) exceed the 64 KiB default.
                limit=_MAX_LINE_BYTES,
            )
        except OSError as exc:
            raise CodexAppServerError(f"Failed to spawn codex app-server: {exc}") from exc

        self._closed = False
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            await asyncio.wait_for(self._handshake(), timeout=_STARTUP_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            await self.close()
            raise CodexAppServerError("codex app-server handshake timed out") from exc
        except CodexAppServerError:
            await self.close()
            raise

        self.logger.info(
            "codex_app_server_started",
            binary=binary,
            model_provider=self._model_provider,
            pid=self._process.pid if self._process else None,
        )

    async def _handshake(self) -> None:
        """Send ``initialize`` then the ``initialized`` notification."""
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "the_tribunal",
                    "title": "The Tribunal",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self._notify("initialized", {})

    async def close(self) -> None:
        """Terminate the child process and release resources."""
        self._closed = True

        if self._process is not None and self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._process.kill()
                with contextlib.suppress(Exception):
                    await self._process.wait()

        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._reader_task = None
        self._stderr_task = None

        for future in self._pending.values():
            if not future.done():
                future.set_exception(CodexAppServerError("codex app-server closed"))
        self._pending.clear()
        self._notifications.clear()
        self._process = None
        self._thread_id = None

    # ------------------------------------------------------------------
    # JSON-RPC plumbing
    # ------------------------------------------------------------------

    async def _read_stdout(self) -> None:
        """Dispatch responses and notifications from the child's stdout."""
        assert self._process is not None
        stream = self._process.stdout
        if stream is None:  # pragma: no cover - defensive
            return

        while True:
            try:
                line = await stream.readline()
            except (asyncio.LimitOverrunError, ValueError):
                # readline() does not consume the offending data, so retrying
                # would spin on the same bytes forever. The stream is wedged.
                self.logger.error("codex_app_server_line_too_long", limit=_MAX_LINE_BYTES)
                break
            if not line:
                break

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # The app-server may emit non-JSON banner lines on startup.
                self.logger.debug(
                    "codex_app_server_non_json", preview=line[:120].decode("utf-8", "replace")
                )
                continue
            if not isinstance(message, dict):
                continue

            self._dispatch(message)

        self._fail_pending(CodexAppServerError("codex app-server exited"))

    def _dispatch(self, message: dict[str, Any]) -> None:
        """Route one decoded JSON-RPC message."""
        message_id = message.get("id")
        if message_id is not None:
            future = self._pending.pop(message_id, None)
            if future is not None and not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        if not isinstance(method, str):
            return
        params = message.get("params")
        payload = params if isinstance(params, dict) else {}
        for queue in self._notifications.get(method, []):
            queue.put_nowait(payload)

    def _fail_pending(self, error: Exception) -> None:
        """Resolve all in-flight requests with an error."""
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _read_stderr(self) -> None:
        """Keep a bounded tail of child stderr for diagnostics."""
        assert self._process is not None
        stream = self._process.stderr
        if stream is None:  # pragma: no cover - defensive
            return
        while True:
            try:
                line = await stream.readline()
            except (asyncio.LimitOverrunError, ValueError):
                # Same non-consuming behaviour as stdout: retrying would spin.
                # Diagnostics stop here, but the call itself keeps running.
                self.logger.warning("codex_app_server_stderr_line_too_long")
                break
            if not line:
                break
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            self._stderr_tail.append(text)
            del self._stderr_tail[:-20]
            self.logger.debug("codex_app_server_stderr", line=text[:500])

    async def _send(self, message: dict[str, Any]) -> None:
        """Write one newline-delimited JSON-RPC message to the child."""
        if self._process is None or self._process.stdin is None:
            raise CodexAppServerError("codex app-server is not running")
        data = json.dumps(message).encode() + b"\n"
        async with self._write_lock:
            self._process.stdin.write(data)
            await self._process.stdin.drain()

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        await self._send({"method": method, "params": params})

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and await its result.

        Raises:
            CodexAppServerError: On transport failure, timeout, or an error reply.
            CodexAuthError: When the reply indicates a missing/invalid login.
        """
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._send({"method": method, "id": request_id, "params": params})
            message = await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise CodexAppServerError(f"{method} timed out after {timeout}s") from exc
        finally:
            self._pending.pop(request_id, None)

        error = message.get("error")
        if error:
            detail = error.get("message", "") if isinstance(error, dict) else str(error)
            if _looks_like_auth_error(detail):
                raise CodexAuthError(
                    "codex app-server is not signed in to a ChatGPT account. "
                    f"Run `codex login` on the host. ({detail})"
                )
            raise CodexAppServerError(f"{method} failed: {detail}")

        result = message.get("result")
        return result if isinstance(result, dict) else {}

    @contextlib.contextmanager
    def subscribe(self, method: str) -> Any:
        """Subscribe to a notification method for the duration of the context."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._notifications.setdefault(method, []).append(queue)
        try:
            yield queue
        finally:
            subscribers = self._notifications.get(method, [])
            if queue in subscribers:
                subscribers.remove(queue)

    # ------------------------------------------------------------------
    # Realtime session control
    # ------------------------------------------------------------------

    async def _start_thread(self) -> str:
        """Open a Codex thread and return its id."""
        params: dict[str, Any] = {"modelProvider": self._model_provider}
        if self._cwd:
            params["cwd"] = self._cwd
        if self._model:
            # A non-ChatGPT-valid default model makes delegated turns fail 400.
            params["model"] = self._model

        result = await self._request("thread/start", params)
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexAppServerError("thread/start returned no thread id")
        self._thread_id = thread_id
        return thread_id

    async def start_realtime(
        self,
        offer_sdp: str,
        options: RealtimeStartOptions,
    ) -> RealtimeSessionHandle:
        """Start a realtime session and return the SDP answer.

        Retries once on a stale thread or a leftover realtime session, which is
        the common state after an app-server restart or an aborted call.
        """
        if not self.is_running:
            await self.start()

        last_error: Exception | None = None
        for attempt in (1, 2):
            thread_id = self._thread_id or await self._start_thread()
            try:
                return await self._start_realtime_once(thread_id, offer_sdp, options)
            except CodexAuthError:
                raise
            except CodexAppServerError as exc:
                last_error = exc
                detail = str(exc).lower()
                if attempt == 2:
                    break
                if "thread not found" in detail:
                    self.logger.info("codex_thread_stale_recreating")
                    self._thread_id = None
                    continue
                if "already" in detail:
                    self.logger.info("codex_realtime_stale_stopping", thread_id=thread_id)
                    with contextlib.suppress(CodexAppServerError):
                        await self.stop_realtime(thread_id)
                    continue
                break

        raise CodexAppServerError(
            f"Could not start Codex realtime session: {last_error}"
        ) from last_error

    async def _start_realtime_once(
        self,
        thread_id: str,
        offer_sdp: str,
        options: RealtimeStartOptions,
    ) -> RealtimeSessionHandle:
        """Issue ``thread/realtime/start`` and collect the SDP answer."""
        with (
            self.subscribe("thread/realtime/sdp") as sdp_queue,
            self.subscribe("thread/realtime/started") as started_queue,
        ):
            await self._request(
                "thread/realtime/start",
                options.to_params(thread_id, offer_sdp),
                timeout=_SDP_TIMEOUT_SECONDS,
            )

            try:
                sdp_params = await asyncio.wait_for(sdp_queue.get(), timeout=_SDP_TIMEOUT_SECONDS)
            except TimeoutError as exc:
                raise CodexAppServerError("No SDP answer from codex app-server") from exc

            answer = sdp_params.get("sdp")
            if not isinstance(answer, str) or not answer:
                raise CodexAppServerError("codex app-server returned an empty SDP answer")

            session_id: str | None = None
            with contextlib.suppress(TimeoutError):
                started = await asyncio.wait_for(started_queue.get(), timeout=5.0)
                candidate = started.get("realtimeSessionId")
                if isinstance(candidate, str):
                    session_id = candidate

        self.logger.info(
            "codex_realtime_started",
            thread_id=thread_id,
            session_id=session_id,
            version=options.version,
            model=REALTIME_MODEL,
            voice=options.voice,
        )
        return RealtimeSessionHandle(
            thread_id=thread_id,
            answer_sdp=answer,
            session_id=session_id,
        )

    async def stop_realtime(self, thread_id: str | None = None) -> None:
        """Hang up the realtime session on a thread."""
        target = thread_id or self._thread_id
        if not target or not self.is_running:
            return
        with contextlib.suppress(CodexAppServerError):
            await self._request("thread/realtime/stop", {"threadId": target}, timeout=10.0)

    @property
    def stderr_tail(self) -> list[str]:
        """Recent child stderr lines, for error reporting."""
        return list(self._stderr_tail)


def _looks_like_auth_error(detail: str) -> bool:
    """Heuristically detect a missing or rejected ChatGPT login."""
    lowered = detail.lower()
    return any(
        marker in lowered
        for marker in ("not logged in", "login", "unauthorized", "401", "auth.json")
    )
