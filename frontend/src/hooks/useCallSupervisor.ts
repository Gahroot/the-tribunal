"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiPost } from "@/lib/api";
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

  const wsRef = useRef<WebSocket | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playheadRef = useRef(0);

  // Barge (mic) resources.
  const micStreamRef = useRef<MediaStream | null>(null);
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
    if (playbackCtxRef.current) {
      void playbackCtxRef.current.close();
      playbackCtxRef.current = null;
    }
    playheadRef.current = 0;
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  }, [stopMic]);

  const disconnect = useCallback(() => {
    cleanup();
    setStatus("idle");
    setIsBarging(false);
    setError(null);
  }, [cleanup]);

  useEffect(() => cleanup, [cleanup]);

  // Schedule a decoded PCM16/24kHz frame for gapless playback.
  const playFrame = useCallback((bytes: Uint8Array) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

    const buffer = ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, playheadRef.current);
    source.start(startAt);
    playheadRef.current = startAt + buffer.duration;
  }, []);

  const connect = useCallback(async () => {
    if (!callId) return;
    setStatus("connecting");
    setError(null);

    let ticket: string;
    try {
      const resp = await apiPost<{ ticket: string }>("/api/v1/auth/ws-ticket");
      ticket = resp.ticket;
    } catch {
      setError("Not authenticated. Please log in again.");
      setStatus("error");
      return;
    }

    playbackCtxRef.current = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });

    const url = `${getBackendWsUrl()}/voice/supervise/${workspaceId}/${callId}?token=${encodeURIComponent(ticket)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "monitor" }));
    };

    ws.onmessage = (event) => {
      let message: { type: string; data?: string; message?: string };
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
          if (message.data) playFrame(base64ToBytes(message.data));
          break;
        case "barge_started":
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
          disconnect();
          break;
        case "error":
          setError(message.message ?? "Supervision error");
          break;
      }
    };

    ws.onerror = () => {
      setError("Supervision connection error");
      setStatus("error");
    };

    ws.onclose = () => {
      setStatus((prev) => (prev === "error" ? prev : "ended"));
      stopMic();
      setIsBarging(false);
    };
  }, [callId, workspaceId, playFrame, disconnect, stopMic]);

  const whisper = useCallback((text: string) => {
    const trimmed = text.trim();
    const ws = wsRef.current;
    if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "whisper", text: trimmed }));
  }, []);

  const startBarge = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: MIC_SAMPLE_RATE,
        },
      });
      micStreamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: MIC_SAMPLE_RATE });
      micCtxRef.current = ctx;
      micSourceRef.current = ctx.createMediaStreamSource(stream);
      micProcessorRef.current = ctx.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);

      micProcessorRef.current.onaudioprocess = (e) => {
        const sock = wsRef.current;
        if (!sock || sock.readyState !== WebSocket.OPEN) return;
        const data = float32ToBase64Pcm16(e.inputBuffer.getChannelData(0));
        sock.send(JSON.stringify({ type: "barge_audio", data }));
      };

      micSourceRef.current.connect(micProcessorRef.current);
      micProcessorRef.current.connect(ctx.destination);

      ws.send(JSON.stringify({ type: "barge" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access failed");
    }
  }, []);

  const stopBarge = useCallback(() => {
    const ws = wsRef.current;
    stopMic();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "unbarge" }));
    }
    setIsBarging(false);
  }, [stopMic]);

  return {
    status,
    error,
    isBarging,
    connect,
    disconnect,
    whisper,
    startBarge,
    stopBarge,
  };
}
