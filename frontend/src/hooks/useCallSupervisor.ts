"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiPost } from "@/lib/api";
import { createPcmResampler } from "@/lib/audio/pcm-resampler";
import { getBackendWsUrl } from "@/lib/utils/backend-url";

/**
 * Operator-side live-call supervision hook.
 *
 * Connects to the backend supervisor WebSocket
 * (`/voice/supervise/{workspaceId}/{callId}`) and exposes the three control
 * surfaces: **listen** (play the live call audio), **whisper** (inject private
 * AI guidance), and **barge** (take over the call with the operator's mic).
 *
 * Audio formats mirror the backend contract:
 * - Inbound `audio` frames are PCM16 @ 24kHz, base64-encoded.
 * - Outbound barge `barge_audio` frames are PCM16 @ 16kHz, base64-encoded.
 */

export type SupervisorStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "error"
  | "ended";

const PLAYBACK_SAMPLE_RATE = 24000;
const MIC_SAMPLE_RATE = 16000;
const MIC_BUFFER_SIZE = 4096;

interface UseCallSupervisorOptions {
  workspaceId: string;
  callId: string | null;
}

interface UseCallSupervisor {
  status: SupervisorStatus;
  error: string | null;
  isBarging: boolean;
  whisperPending: boolean;
  whisperAcknowledged: number;
  connect: () => Promise<void>;
  disconnect: () => void;
  whisper: (text: string) => void;
  startBarge: () => Promise<void>;
  stopBarge: () => void;
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function float32ToBase64Pcm16(input: Float32Array): string {
  const pcm16 = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm16.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export function useCallSupervisor({
  workspaceId,
  callId,
}: UseCallSupervisorOptions): UseCallSupervisor {
  const [status, setStatus] = useState<SupervisorStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isBarging, setIsBarging] = useState(false);
  const [whisperPending, setWhisperPending] = useState(false);
  const [whisperAcknowledged, setWhisperAcknowledged] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const generationRef = useRef(0);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playheadRef = useRef<Record<string, number>>({ caller: 0, agent: 0 });

  // Barge (mic) resources.
  const micStreamRef = useRef<MediaStream | null>(null);
  const bargePendingRef = useRef(false);
  const micCtxRef = useRef<AudioContext | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micProcessorRef = useRef<ScriptProcessorNode | null>(null);

  const stopMic = useCallback(() => {
    if (micProcessorRef.current) {
      micProcessorRef.current.disconnect();
      micProcessorRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (micCtxRef.current) {
      void micCtxRef.current.close();
      micCtxRef.current = null;
    }
  }, []);

  const cleanup = useCallback(() => {
    stopMic();
    bargePendingRef.current = false;
    if (playbackCtxRef.current) {
      void playbackCtxRef.current.close();
      playbackCtxRef.current = null;
    }
    playheadRef.current = { caller: 0, agent: 0 };
    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.close();
    }
  }, [stopMic]);

  const disconnect = useCallback(() => {
    generationRef.current++;
    cleanup();
    setStatus("idle");
    setIsBarging(false);
    setWhisperPending(false);
    setError(null);
  }, [cleanup]);

  useEffect(() => () => {
    generationRef.current++;
    cleanup();
  }, [cleanup]);

  // Schedule a decoded PCM16/24kHz frame for gapless playback.
  const playFrame = useCallback((bytes: Uint8Array, track: string) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    const count = Math.floor(bytes.byteLength / 2);
    if (!count) return;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const float32 = new Float32Array(count);
    for (let i = 0; i < count; i++) float32[i] = view.getInt16(i * 2, true) / 32768;

    const buffer = ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    // Keep caller and agent on separate clocks so their audio overlaps rather
    // than playing one after the other. Drop stale backlog to stay live.
    const startAt = Math.max(now, Math.min(playheadRef.current[track] ?? now, now + 0.5));
    source.start(startAt);
    playheadRef.current[track] = startAt + buffer.duration;
  }, []);

  const connect = useCallback(async () => {
    if (!callId || wsRef.current) return;
    const generation = ++generationRef.current;
    setStatus("connecting");
    setError(null);

    let ticket: string;
    try {
      const resp = await apiPost<{ ticket: string }>("/api/v1/auth/ws-ticket");
      if (generation !== generationRef.current) return;
      ticket = resp.ticket;
    } catch {
      if (generation !== generationRef.current) return;
      setError("Not authenticated. Please log in again.");
      setStatus("error");
      return;
    }

    try {
      // AudioBuffer keeps the stream's 24 kHz rate; the browser resamples it
      // for its actual output device rate.
      playbackCtxRef.current = new AudioContext();
      await playbackCtxRef.current.resume();
      if (generation !== generationRef.current) {
        cleanup();
        return;
      }
    } catch {
      cleanup();
      if (generation !== generationRef.current) return;
      setError("Audio playback is unavailable in this browser");
      setStatus("error");
      return;
    }

    const url = `${getBackendWsUrl()}/voice/supervise/${encodeURIComponent(workspaceId)}/${encodeURIComponent(callId)}?token=${encodeURIComponent(ticket)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "monitor" }));
    };

    ws.onmessage = (event) => {
      let message: { type: string; data?: string; track?: string; message?: string };
      try {
        message = JSON.parse(event.data as string);
      } catch {
        return;
      }
      switch (message.type) {
        case "monitoring":
          setStatus("listening");
          break;
        case "audio":
          if (message.data && (message.track === "caller" || message.track === "agent")) {
            playFrame(base64ToBytes(message.data), message.track);
          }
          break;
        case "whispered":
          setWhisperAcknowledged((count) => count + 1);
          setWhisperPending(false);
          setError(null);
          break;
        case "barge_started":
          bargePendingRef.current = false;
          setIsBarging(true);
          break;
        case "barge_stopped":
          setIsBarging(false);
          break;
        case "ping":
          ws.send(JSON.stringify({ type: "pong" }));
          break;
        case "call_ended":
          setStatus("ended");
          generationRef.current++;
          cleanup();
          setIsBarging(false);
          setWhisperPending(false);
          break;
        case "error":
          if (bargePendingRef.current) {
            stopMic();
            bargePendingRef.current = false;
          }
          setWhisperPending(false);
          setError(message.message ?? "Supervision error");
          setStatus((current) => current === "connecting" ? "error" : current);
          break;
      }
    };

    ws.onerror = () => {
      setError("Supervision connection error");
      setStatus("error");
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      setStatus((prev) => (prev === "error" ? prev : "ended"));
      cleanup();
      setIsBarging(false);
      setWhisperPending(false);
    };
  }, [callId, workspaceId, playFrame, cleanup, stopMic]);

  const whisper = useCallback((text: string) => {
    const trimmed = text.trim();
    const ws = wsRef.current;
    if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return;
    setWhisperPending(true);
    setError(null);
    ws.send(JSON.stringify({ type: "whisper", text: trimmed }));
  }, []);

  const startBarge = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || bargePendingRef.current || micStreamRef.current) return;
    bargePendingRef.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: MIC_SAMPLE_RATE,
        },
      });
      if (wsRef.current !== ws || ws.readyState !== WebSocket.OPEN) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      micStreamRef.current = stream;
      stream.getAudioTracks()[0]?.addEventListener("ended", () => {
        if (wsRef.current !== ws) return;
        stopMic();
        bargePendingRef.current = false;
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "unbarge" }));
        setIsBarging(false);
        setError("Microphone disconnected. AI control restored.");
      }, { once: true });
      const ctx = new AudioContext();
      micCtxRef.current = ctx;
      const resample = createPcmResampler(ctx.sampleRate, MIC_SAMPLE_RATE);
      micSourceRef.current = ctx.createMediaStreamSource(stream);
      micProcessorRef.current = ctx.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);

      micProcessorRef.current.onaudioprocess = (e) => {
        const sock = wsRef.current;
        if (!sock || sock !== ws || sock.readyState !== WebSocket.OPEN || sock.bufferedAmount > 65536) return;
        const samples = resample(e.inputBuffer.getChannelData(0));
        if (samples.length === 0) return;
        const data = float32ToBase64Pcm16(samples);
        sock.send(JSON.stringify({ type: "barge_audio", data }));
      };

      micSourceRef.current.connect(micProcessorRef.current);
      const silentOutput = ctx.createGain();
      silentOutput.gain.value = 0;
      micProcessorRef.current.connect(silentOutput);
      silentOutput.connect(ctx.destination);

      ws.send(JSON.stringify({ type: "barge" }));
    } catch (err) {
      stopMic();
      bargePendingRef.current = false;
      setError(err instanceof Error ? err.message : "Microphone access failed");
    }
  }, [stopMic]);

  const stopBarge = useCallback(() => {
    const ws = wsRef.current;
    stopMic();
    bargePendingRef.current = false;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "unbarge" }));
    }
    setIsBarging(false);
  }, [stopMic]);

  return {
    status,
    error,
    isBarging,
    whisperPending,
    whisperAcknowledged,
    connect,
    disconnect,
    whisper,
    startBarge,
    stopBarge,
  };
}
