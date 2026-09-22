"""Tests for the Codex app-server broker.

These drive a scripted fake ``codex app-server`` written in Python, so the
JSON-RPC framing, handshake, SDP exchange, and recovery paths are exercised
against a real subprocess without needing the codex CLI or a ChatGPT login.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
import textwrap

import pytest

from app.services.ai.codex_app_server import (
    DEFAULT_CODEX_VOICE,
    REALTIME_MODEL,
    REALTIME_PROTOCOL_VERSION,
    CodexAppServerBroker,
    CodexAppServerError,
    CodexAuthError,
    RealtimeStartOptions,
    build_child_env,
    resolve_codex_binary,
)

_FAKE_SERVER = """
import json, os, sys

MODE = {mode!r}
PARAMS_FILE = os.environ.get("CODEX_FAKE_PARAMS_FILE")
THREAD_PARAMS_FILE = os.environ.get("CODEX_FAKE_THREAD_PARAMS_FILE")
started_realtime = 0

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()

# A banner line the broker must tolerate and skip.
send_banner = True
if send_banner:
    sys.stdout.write("codex app-server ready\\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        send({{"id": msg_id, "result": {{"userAgent": "fake"}}}})
    elif method == "initialized":
        continue
    elif method == "thread/start":
        if THREAD_PARAMS_FILE:
            with open(THREAD_PARAMS_FILE, "w") as fh:
                json.dump(msg.get("params", {{}}), fh)
        if MODE == "auth_error":
            send({{"id": msg_id, "error": {{"message": "Not logged in. Run codex login."}}}})
        else:
            send({{"id": msg_id, "result": {{"thread": {{"id": "thr_fake"}}}}}})
    elif method == "thread/realtime/start":
        started_realtime += 1
        if MODE == "stale_thread" and started_realtime == 1:
            send({{"id": msg_id, "error": {{"message": "thread not found"}}}})
            continue
        if MODE == "stale_session" and started_realtime == 1:
            send({{"id": msg_id, "error": {{"message": "realtime session already active"}}}})
            continue
        if MODE == "no_sdp":
            send({{"id": msg_id, "result": {{}}}})
            continue
        send({{"id": msg_id, "result": {{}}}})
        params = msg.get("params", {{}})
        if PARAMS_FILE:
            with open(PARAMS_FILE, "w") as fh:
                json.dump(params, fh)
        send({{"method": "thread/realtime/sdp", "params": {{"sdp": "v=0 answer"}}}})
        send({{
            "method": "thread/realtime/started",
            "params": {{"realtimeSessionId": "rt_fake"}},
        }})
    elif method == "thread/realtime/stop":
        send({{"id": msg_id, "result": {{}}}})
    elif method == "flood":
        # One line past any sane limit, never newline-terminated.
        sys.stdout.write("x" * 200000)
        sys.stdout.flush()
    else:
        send({{"id": msg_id, "result": {{}}}})
"""


@pytest.fixture
def fake_codex(tmp_path):
    """Build a fake ``codex`` executable; returns a factory taking a mode."""

    def _make(mode: str = "ok") -> str:
        script = tmp_path / f"codex_{mode}.py"
        script.write_text(_FAKE_SERVER.format(mode=mode))
        binary = tmp_path / f"codex-{mode}"
        binary.write_text(
            textwrap.dedent(f"""\
            #!{sys.executable}
            import runpy, sys
            sys.argv = [sys.argv[0]]
            runpy.run_path({str(script)!r}, run_name="__main__")
            """)
        )
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(binary)

    return _make


@pytest.mark.asyncio
async def test_start_realtime_returns_sdp_answer(fake_codex):
    """Handshake, thread start, and SDP exchange produce a usable answer."""
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"))
    try:
        handle = await broker.start_realtime(
            "v=0 offer",
            RealtimeStartOptions(prompt="You are a helpful agent."),
        )
        assert handle.answer_sdp == "v=0 answer"
        assert handle.thread_id == "thr_fake"
        assert handle.session_id == "rt_fake"
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_start_realtime_sends_v3_protocol_params(fake_codex, tmp_path, monkeypatch):
    """The session must request protocol v3, which maps to gpt-live-1-codex."""
    params_file = tmp_path / "realtime_params.json"
    monkeypatch.setenv("CODEX_FAKE_PARAMS_FILE", str(params_file))
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"))
    try:
        await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
        params = json.loads(params_file.read_text())
        assert params["version"] == REALTIME_PROTOCOL_VERSION == "v3"
        assert params["transport"] == {"type": "webrtc", "sdp": "v=0 offer"}
        assert params["outputModality"] == "audio"
        assert params["clientManagedHandoffs"] is True
        assert params["delegationAckFiller"] is True
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_thread_model_is_forwarded(fake_codex, tmp_path, monkeypatch):
    """LIVE_VOICE_THREAD_MODEL must reach the child, not be silently dropped."""
    params_file = tmp_path / "thread_params.json"
    monkeypatch.setenv("CODEX_FAKE_THREAD_PARAMS_FILE", str(params_file))
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"), model="gpt-5.5-codex")
    try:
        await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
        params = json.loads(params_file.read_text())
        assert params["model"] == "gpt-5.5-codex"
        assert params["modelProvider"] == "openai"
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_thread_model_omitted_when_unset(fake_codex, tmp_path, monkeypatch):
    """With no override the child picks its own ChatGPT-valid default."""
    params_file = tmp_path / "thread_params_default.json"
    monkeypatch.setenv("CODEX_FAKE_THREAD_PARAMS_FILE", str(params_file))
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"))
    try:
        await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
        assert "model" not in json.loads(params_file.read_text())
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_auth_error_is_actionable(fake_codex):
    """A missing login raises CodexAuthError telling the operator what to run."""
    broker = CodexAppServerBroker(binary_path=fake_codex("auth_error"))
    try:
        with pytest.raises(CodexAuthError, match="codex login"):
            await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_stale_thread_is_recreated(fake_codex):
    """`thread not found` recreates the thread and retries once."""
    broker = CodexAppServerBroker(binary_path=fake_codex("stale_thread"))
    try:
        handle = await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
        assert handle.answer_sdp == "v=0 answer"
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_stale_realtime_session_is_stopped_then_retried(fake_codex):
    """An `already active` session is hung up and the start retried."""
    broker = CodexAppServerBroker(binary_path=fake_codex("stale_session"))
    try:
        handle = await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
        assert handle.answer_sdp == "v=0 answer"
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_missing_sdp_answer_fails_cleanly(fake_codex, monkeypatch):
    """No SDP notification surfaces an error rather than hanging forever."""
    monkeypatch.setattr("app.services.ai.codex_app_server._SDP_TIMEOUT_SECONDS", 1.0)
    broker = CodexAppServerBroker(binary_path=fake_codex("no_sdp"))
    try:
        with pytest.raises(CodexAppServerError):
            await broker.start_realtime("v=0 offer", RealtimeStartOptions(prompt="hi"))
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_overlong_line_does_not_spin_forever(fake_codex, monkeypatch):
    """A line past the cap ends the reader instead of retrying the same bytes.

    ``StreamReader.readline`` does not consume the offending data, so a
    ``continue`` here would busy-loop at 100% CPU for the rest of the call.
    """
    monkeypatch.setattr("app.services.ai.codex_app_server._MAX_LINE_BYTES", 4096)
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"))
    try:
        await broker.start()
        await broker._notify("flood", {})

        # The reader must terminate on its own rather than spinning.
        reader = broker._reader_task
        assert reader is not None
        await asyncio.wait_for(reader, timeout=5.0)

        # In-flight work is failed rather than left hanging forever.
        with pytest.raises(CodexAppServerError):
            await broker._request("thread/start", {}, timeout=2.0)
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_close_terminates_child(fake_codex):
    """Closing the broker stops the child process."""
    broker = CodexAppServerBroker(binary_path=fake_codex("ok"))
    await broker.start()
    assert broker.is_running
    await broker.close()
    assert not broker.is_running


def test_configured_binary_must_be_executable():
    """An explicitly configured path names itself in the error."""
    with pytest.raises(CodexAppServerError, match="not executable"):
        resolve_codex_binary("/nonexistent/codex")


def test_undiscoverable_binary_raises_with_install_hint(monkeypatch):
    """With nothing on PATH, the error explains how to install and log in."""
    monkeypatch.setattr("app.services.ai.codex_app_server.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "app.services.ai.codex_app_server._BINARY_CANDIDATES",
        ("/nonexistent/a", "/nonexistent/b"),
    )
    with pytest.raises(CodexAppServerError, match="codex login"):
        resolve_codex_binary(None)


def test_child_env_strips_api_keys(monkeypatch, tmp_path):
    """API keys must not leak into the child, or it bills the API instead."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-propagate")
    monkeypatch.setenv("CODEX_API_KEY", "codex-should-not-propagate")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.invalid")

    binary = tmp_path / "bin" / "codex"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")

    env = build_child_env(str(binary))

    assert "OPENAI_API_KEY" not in env
    assert "CODEX_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
    assert str(binary.parent) in env["PATH"].split(os.pathsep)


def test_start_options_reject_unknown_voice():
    """An unsupported voice falls back instead of failing the call."""
    params = RealtimeStartOptions(prompt="hi", voice="not-a-voice").to_params("thr", "sdp")
    assert params["voice"] == DEFAULT_CODEX_VOICE


def test_realtime_model_is_gpt_live_codex():
    """Protocol v3 is the gpt-live-1-codex lane."""
    assert REALTIME_MODEL == "gpt-live-1-codex"
