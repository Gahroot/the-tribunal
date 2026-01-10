"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, MicOff, Phone, PhoneOff, Volume2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface VoiceTestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string;
  agentName: string;
  workspaceId: string;
}

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

export function VoiceTestDialog({
  open,
  onOpenChange,
  agentId,
  agentName,
  workspaceId,
}: VoiceTestDialogProps) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");
  const [isMuted, setIsMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const playbackQueueRef = useRef<Float32Array[]>([]);
  const isPlayingRef = useRef(false);

  // Clean up on unmount or dialog close
  useEffect(() => {
    if (!open) {
      disconnect();
    }
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const disconnect = useCallback(() => {
    // Stop audio processing
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (playbackContextRef.current) {
      void playbackContextRef.current.close();
      playbackContextRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
      }
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnectionStatus("disconnected");
    setIsMuted(false);
    setError(null);
    playbackQueueRef.current = [];
    isPlayingRef.current = false;
    setIsPlaying(false);
  }, []);

  const playAudioQueue = useCallback(async () => {
    if (isPlayingRef.current || playbackQueueRef.current.length === 0) {
      return;
    }

    isPlayingRef.current = true;
    setIsPlaying(true);

    while (playbackQueueRef.current.length > 0) {
      const audioData = playbackQueueRef.current.shift();
      if (!audioData || !playbackContextRef.current) break;

      const audioBuffer = playbackContextRef.current.createBuffer(
        1,
        audioData.length,
        SAMPLE_RATE
      );
      audioBuffer.getChannelData(0).set(audioData);

      const source = playbackContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(playbackContextRef.current.destination);

      await new Promise<void>((resolve) => {
        source.onended = () => resolve();
        source.start();
      });
    }

    isPlayingRef.current = false;
    setIsPlaying(false);
  }, []);

  const connect = useCallback(async () => {
    setConnectionStatus("connecting");
    setError(null);

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: SAMPLE_RATE,
        },
      });
      mediaStreamRef.current = stream;

      // Create audio context for recording
      audioContextRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);

      // Create audio context for playback
      playbackContextRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });

      // Create processor for capturing audio
      processorRef.current = audioContextRef.current.createScriptProcessor(
        BUFFER_SIZE,
        1,
        1
      );

      // Connect WebSocket
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = process.env.NEXT_PUBLIC_API_URL?.replace(/^https?:\/\//, "") || "localhost:8000";
      const wsUrl = `${wsProtocol}//${wsHost}/voice/test/${workspaceId}/${agentId}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Send start message
        ws.send(JSON.stringify({ type: "start" }));
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data as string) as {
            type: string;
            data?: string;
            message?: string;
            role?: string;
            text?: string;
          };

          switch (message.type) {
            case "connected":
              setConnectionStatus("connected");
              // Start audio capture after connected
              if (sourceRef.current && processorRef.current && audioContextRef.current) {
                sourceRef.current.connect(processorRef.current);
                processorRef.current.connect(audioContextRef.current.destination);
              }
              break;

            case "audio":
              if (message.data) {
                // Decode base64 PCM16 audio
                const binaryString = atob(message.data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                  bytes[i] = binaryString.charCodeAt(i);
                }

                // Convert PCM16 to Float32
                const int16Array = new Int16Array(bytes.buffer);
                const float32Array = new Float32Array(int16Array.length);
                for (let i = 0; i < int16Array.length; i++) {
                  float32Array[i] = int16Array[i] / 32768;
                }

                playbackQueueRef.current.push(float32Array);
                void playAudioQueue();
              }
              break;

            case "error":
              setError(message.message || "Unknown error");
              setConnectionStatus("error");
              break;

            case "stopped":
              disconnect();
              break;
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection error");
        setConnectionStatus("error");
      };

      ws.onclose = () => {
        if (connectionStatus === "connected" || connectionStatus === "connecting") {
          setConnectionStatus("disconnected");
        }
      };

      // Set up audio processing
      processorRef.current.onaudioprocess = (e) => {
        if (isMuted || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          return;
        }

        const inputData = e.inputBuffer.getChannelData(0);

        // Convert Float32 to PCM16
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Convert to base64
        const bytes = new Uint8Array(pcm16.buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        const base64 = btoa(binary);

        wsRef.current.send(JSON.stringify({
          type: "audio",
          data: base64,
        }));
      };

    } catch (err) {
      console.error("Connection error:", err);
      setError(err instanceof Error ? err.message : "Failed to connect");
      setConnectionStatus("error");
      disconnect();
    }
  }, [agentId, workspaceId, connectionStatus, disconnect, isMuted, playAudioQueue]);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => !prev);
  }, []);

  const handleCallToggle = useCallback(() => {
    if (connectionStatus === "connected" || connectionStatus === "connecting") {
      disconnect();
    } else {
      void connect();
    }
  }, [connectionStatus, connect, disconnect]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Test Voice Agent</DialogTitle>
          <DialogDescription>
            Test &ldquo;{agentName}&rdquo; with your microphone. Speak naturally and the
            agent will respond.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center gap-6 py-6">
          {/* Status indicator */}
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "h-3 w-3 rounded-full",
                connectionStatus === "connected" && "bg-green-500",
                connectionStatus === "connecting" && "bg-yellow-500 animate-pulse",
                connectionStatus === "disconnected" && "bg-gray-400",
                connectionStatus === "error" && "bg-red-500"
              )}
            />
            <span className="text-sm text-muted-foreground capitalize">
              {connectionStatus}
            </span>
            {isPlaying && (
              <div className="flex items-center gap-1 text-sm text-primary">
                <Volume2 className="h-4 w-4 animate-pulse" />
                <span>Speaking...</span>
              </div>
            )}
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Call controls */}
          <div className="flex items-center gap-4">
            {/* Mute button */}
            <Button
              variant="outline"
              size="icon"
              className={cn(
                "h-14 w-14 rounded-full",
                isMuted && "bg-destructive/10 text-destructive hover:bg-destructive/20"
              )}
              onClick={toggleMute}
              disabled={connectionStatus !== "connected"}
            >
              {isMuted ? <MicOff className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
            </Button>

            {/* Call button */}
            <Button
              variant={connectionStatus === "connected" ? "destructive" : "default"}
              size="icon"
              className="h-16 w-16 rounded-full"
              onClick={handleCallToggle}
              disabled={connectionStatus === "connecting"}
            >
              {connectionStatus === "connecting" ? (
                <Loader2 className="h-7 w-7 animate-spin" />
              ) : connectionStatus === "connected" ? (
                <PhoneOff className="h-7 w-7" />
              ) : (
                <Phone className="h-7 w-7" />
              )}
            </Button>

            {/* Placeholder for symmetry */}
            <div className="h-14 w-14" />
          </div>

          {/* Instructions */}
          <p className="text-center text-xs text-muted-foreground">
            {connectionStatus === "disconnected" && "Click the phone button to start testing"}
            {connectionStatus === "connecting" && "Connecting to voice agent..."}
            {connectionStatus === "connected" && "Speak into your microphone"}
            {connectionStatus === "error" && "Connection failed. Try again."}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
