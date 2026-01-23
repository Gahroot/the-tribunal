"use client";

import { useEffect, useState, useCallback, useRef, use } from "react";
import { Mic, MicOff, X, Phone } from "lucide-react";
import { useSearchParams } from "next/navigation";

interface AgentConfig {
  public_id: string;
  name: string;
  greeting_message: string | null;
  button_text: string;
  theme: "light" | "dark" | "auto";
  position: string;
  primary_color: string;
  language: string;
  voice: string;
  channel_mode: string;
}

interface TokenResponse {
  client_secret: { value: string };
  agent: {
    name: string;
    voice: string;
    instructions: string;
    language: string;
    initial_greeting: string | null;
  };
  model: string;
  tools: Array<{
    type: string;
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  }>;
}

type ConnectionStatus = "idle" | "connecting" | "connected" | "error";
type AgentState = "idle" | "listening" | "thinking" | "speaking";

type WebRTCResources = {
  peerConnection: RTCPeerConnection | null;
  dataChannel: RTCDataChannel | null;
  audioStream: MediaStream | null;
  audioElement: HTMLAudioElement | null;
};

type AudioResources = {
  audioContext: AudioContext | null;
  analyser: AnalyserNode | null;
  dataArray: Uint8Array<ArrayBuffer> | null;
  animationFrame: number | null;
};

type TranscriptEntry = {
  role: "user" | "assistant";
  content: string;
};

const BAR_COUNT = 24;

interface EmbedPageProps {
  params: Promise<{ publicId: string }>;
}

export default function EmbedPage({ params }: EmbedPageProps) {
  const { publicId } = use(params);
  const searchParams = useSearchParams();
  const theme = (searchParams.get("theme") as "light" | "dark" | "auto") ?? "auto";
  const position = searchParams.get("position") ?? "bottom-right";
  const autostart = searchParams.get("autostart") === "true";

  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isMuted, setIsMuted] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [frequencies, setFrequencies] = useState<number[]>(new Array(BAR_COUNT).fill(0));
  const [smoothedLevel, setSmoothedLevel] = useState(0);

  const webrtcRef = useRef<WebRTCResources>({
    peerConnection: null,
    dataChannel: null,
    audioStream: null,
    audioElement: null,
  });

  const audioRef = useRef<AudioResources>({
    audioContext: null,
    analyser: null,
    dataArray: null,
    animationFrame: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const transcriptRef = useRef<TranscriptEntry[]>([]);
  const currentAssistantTextRef = useRef<string>("");
  const sessionIdRef = useRef<string>("");
  const sessionStartTimeRef = useRef<number>(0);
  const autostartTriggeredRef = useRef(false);

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    if (theme === "auto") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      setResolvedTheme(mediaQuery.matches ? "dark" : "light");
      const handler = (e: MediaQueryListEvent) =>
        setResolvedTheme(e.matches ? "dark" : "light");
      mediaQuery.addEventListener("change", handler);
      return () => mediaQuery.removeEventListener("change", handler);
    }
    setResolvedTheme(theme);
    return undefined;
  }, [theme]);

  // Notify parent window of state changes
  useEffect(() => {
    if (window.parent !== window) {
      window.parent.postMessage({ type: "ai-agent:state", state: agentState }, "*");
    }
  }, [agentState]);

  // Notify parent window of audio level
  useEffect(() => {
    if (window.parent !== window && smoothedLevel > 0.05) {
      window.parent.postMessage({ type: "ai-agent:audio-level", level: smoothedLevel }, "*");
    }
  }, [smoothedLevel]);

  // Fetch agent config
  useEffect(() => {
    async function fetchConfig() {
      try {
        const res = await fetch(`/api/v1/p/embed/${publicId}/config`, {
          headers: { Origin: window.location.origin },
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error((data.detail as string) ?? "Failed to load agent");
        }
        const data = await res.json();
        setConfig(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load agent");
      }
    }
    if (publicId) {
      void fetchConfig();
    }
  }, [publicId]);

  // Audio analysis setup
  const setupAudioAnalysis = useCallback((stream: MediaStream) => {
    try {
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.7;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      audioRef.current = {
        audioContext,
        analyser,
        dataArray,
        animationFrame: null,
      };

      const updateLevel = () => {
        if (audioRef.current.analyser && audioRef.current.dataArray) {
          audioRef.current.analyser.getByteFrequencyData(audioRef.current.dataArray);
          const data = audioRef.current.dataArray;

          const bands: number[] = [];
          const bufferLength = data.length;

          for (let i = 0; i < BAR_COUNT; i++) {
            const startIndex = Math.floor(Math.pow(i / BAR_COUNT, 1.5) * bufferLength);
            const endIndex = Math.floor(Math.pow((i + 1) / BAR_COUNT, 1.5) * bufferLength);

            let sum = 0;
            const count = Math.max(1, endIndex - startIndex);
            for (let j = startIndex; j < endIndex && j < bufferLength; j++) {
              sum += data[j] ?? 0;
            }

            const avg = sum / count / 255;
            bands.push(Math.min(1, avg * 1.8));
          }

          setFrequencies(bands);

          const voiceRange = Array.from(data).slice(0, 16);
          const avg = voiceRange.reduce((a, b) => a + b, 0) / voiceRange.length;
          const normalizedLevel = Math.min(avg / 128, 1);

          setSmoothedLevel((prev) => {
            if (normalizedLevel > prev) {
              return prev + (normalizedLevel - prev) * 0.3;
            } else {
              return prev + (normalizedLevel - prev) * 0.1;
            }
          });
        }

        audioRef.current.animationFrame = requestAnimationFrame(updateLevel);
      };

      updateLevel();
    } catch {
      // Audio analysis not critical
    }
  }, []);

  // Cleanup audio analysis
  const cleanupAudioAnalysis = useCallback(() => {
    if (audioRef.current.animationFrame) {
      cancelAnimationFrame(audioRef.current.animationFrame);
    }
    if (audioRef.current.audioContext) {
      try {
        void audioRef.current.audioContext.close();
      } catch {
        // Ignore cleanup errors
      }
    }
    audioRef.current = {
      audioContext: null,
      analyser: null,
      dataArray: null,
      animationFrame: null,
    };
    setFrequencies(new Array(BAR_COUNT).fill(0));
    setSmoothedLevel(0);
  }, []);

  // Save transcript
  const saveTranscript = useCallback(async () => {
    if (currentAssistantTextRef.current.trim()) {
      transcriptRef.current.push({
        role: "assistant",
        content: currentAssistantTextRef.current.trim(),
      });
      currentAssistantTextRef.current = "";
    }

    if (transcriptRef.current.length === 0 || !sessionIdRef.current) {
      return;
    }

    const transcriptText = transcriptRef.current
      .map((entry) => `[${entry.role === "user" ? "User" : "Assistant"}]: ${entry.content}`)
      .join("\n\n");

    const durationSeconds = sessionStartTimeRef.current
      ? Math.floor((Date.now() - sessionStartTimeRef.current) / 1000)
      : 0;

    try {
      await fetch(`/api/v1/p/embed/${publicId}/transcript`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: window.location.origin,
        },
        body: JSON.stringify({
          session_id: sessionIdRef.current,
          transcript: transcriptText,
          duration_seconds: durationSeconds,
        }),
      });
    } catch {
      // Silently fail
    }

    transcriptRef.current = [];
    sessionIdRef.current = "";
    sessionStartTimeRef.current = 0;
  }, [publicId]);

  // Cleanup function
  const cleanup = useCallback(() => {
    const { peerConnection, dataChannel, audioStream, audioElement } = webrtcRef.current;

    cleanupAudioAnalysis();

    if (dataChannel) {
      try {
        dataChannel.close();
      } catch {
        // Ignore
      }
    }

    if (peerConnection) {
      try {
        peerConnection.close();
      } catch {
        // Ignore
      }
    }

    if (audioStream) {
      try {
        audioStream.getTracks().forEach((track) => track.stop());
      } catch {
        // Ignore
      }
    }

    if (audioElement) {
      try {
        audioElement.srcObject = null;
        audioElement.remove();
      } catch {
        // Ignore
      }
    }

    webrtcRef.current = {
      peerConnection: null,
      dataChannel: null,
      audioStream: null,
      audioElement: null,
    };

    setAgentState("idle");
  }, [cleanupAudioAnalysis]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  // End voice session
  const endSession = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    void saveTranscript();
    cleanup();
    setStatus("idle");
    setIsExpanded(false);

    if (window.parent !== window) {
      window.parent.postMessage({ type: "ai-agent:close" }, "*");
    }
  }, [cleanup, saveTranscript]);

  // Start voice session
  const startSession = useCallback(async () => {
    if (!config) return;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    transcriptRef.current = [];
    currentAssistantTextRef.current = "";
    sessionIdRef.current = crypto.randomUUID();
    sessionStartTimeRef.current = Date.now();

    setStatus("connecting");
    setError(null);
    setIsExpanded(true);
    setAgentState("idle");

    try {
      const tokenRes = await fetch(`/api/v1/p/embed/${publicId}/token`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: window.location.origin,
        },
        signal: abortController.signal,
      });

      if (abortController.signal.aborted) return;

      if (!tokenRes.ok) {
        const errData = await tokenRes.json();
        throw new Error((errData.detail as string) ?? "Failed to get token");
      }

      const tokenData: TokenResponse = await tokenRes.json();
      const ephemeralKey = tokenData.client_secret.value;

      if (abortController.signal.aborted) return;

      const pc = new RTCPeerConnection();
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioTrack = micStream.getAudioTracks()[0];
      if (audioTrack) {
        pc.addTrack(audioTrack);
      }

      setupAudioAnalysis(micStream);

      const dataChannel = pc.createDataChannel("oai-events");

      const audioElement = document.createElement("audio");
      audioElement.autoplay = true;
      pc.ontrack = (event) => {
        audioElement.srcObject = event.streams[0] ?? null;
      };

      webrtcRef.current = {
        peerConnection: pc,
        dataChannel,
        audioStream: micStream,
        audioElement,
      };

      if (abortController.signal.aborted) {
        micStream.getTracks().forEach((track) => track.stop());
        pc.close();
        return;
      }

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      if (abortController.signal.aborted) {
        micStream.getTracks().forEach((track) => track.stop());
        pc.close();
        return;
      }

      const response = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        body: offer.sdp,
        headers: {
          "Content-Type": "application/sdp",
          Authorization: `Bearer ${ephemeralKey}`,
          "OpenAI-Beta": "realtime=v1",
        },
        signal: abortController.signal,
      });

      if (abortController.signal.aborted) {
        micStream.getTracks().forEach((track) => track.stop());
        pc.close();
        return;
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`OpenAI API error (${response.status}): ${errorText}`);
      }

      const answerSdp = await response.text();

      if (abortController.signal.aborted) {
        micStream.getTracks().forEach((track) => track.stop());
        pc.close();
        return;
      }

      await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

      const agentTools = tokenData.tools ?? [];

      dataChannel.onopen = () => {
        if (abortController.signal.aborted) return;
        setStatus("connected");
        setAgentState("listening");

        const sessionConfig: Record<string, unknown> = {
          instructions: tokenData.agent.instructions,
          voice: tokenData.agent.voice,
          input_audio_transcription: { model: "whisper-1" },
          turn_detection: {
            type: "server_vad",
            threshold: 0.5,
            prefix_padding_ms: 300,
            silence_duration_ms: 200,
          },
        };

        if (agentTools.length > 0) {
          sessionConfig.tools = agentTools;
          sessionConfig.tool_choice = "auto";
        }

        const sessionUpdate = { type: "session.update", session: sessionConfig };
        dataChannel.send(JSON.stringify(sessionUpdate));

        if (tokenData.agent.initial_greeting) {
          dataChannel.send(
            JSON.stringify({
              type: "response.create",
              response: {
                instructions: `Start the conversation by saying exactly this (do not add anything else): "${tokenData.agent.initial_greeting}"`,
              },
            })
          );
        }
      };

      const executeToolCall = async (
        callId: string,
        toolName: string,
        args: Record<string, unknown>
      ) => {
        try {
          const toolResponse = await fetch(`/api/v1/p/embed/${publicId}/tool-call`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Origin: window.location.origin,
            },
            body: JSON.stringify({
              tool_name: toolName,
              arguments: args,
            }),
          });

          const result = (await toolResponse.json()) as Record<string, unknown>;

          if (dataChannel.readyState === "open") {
            dataChannel.send(
              JSON.stringify({
                type: "conversation.item.create",
                item: {
                  type: "function_call_output",
                  call_id: callId,
                  output: JSON.stringify(result),
                },
              })
            );
            dataChannel.send(JSON.stringify({ type: "response.create" }));
          }

          if (result.action === "end_call") {
            setTimeout(() => {
              endSession();
            }, 3000);
          }
        } catch (err) {
          if (dataChannel.readyState === "open") {
            dataChannel.send(
              JSON.stringify({
                type: "conversation.item.create",
                item: {
                  type: "function_call_output",
                  call_id: callId,
                  output: JSON.stringify({
                    success: false,
                    error: err instanceof Error ? err.message : "Tool execution failed",
                  }),
                },
              })
            );
            dataChannel.send(JSON.stringify({ type: "response.create" }));
          }
        }
      };

      dataChannel.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "input_audio_buffer.speech_started") {
            setAgentState("listening");
          } else if (data.type === "input_audio_buffer.speech_stopped") {
            setAgentState("thinking");
          } else if (data.type === "response.audio.delta") {
            setAgentState("speaking");
          } else if (data.type === "response.audio.done") {
            setAgentState("listening");
          } else if (data.type === "response.done") {
            setAgentState("listening");
          } else if (data.type === "response.function_call_arguments.done") {
            const callId = data.call_id as string;
            const toolName = data.name as string;
            const argsJson = data.arguments;

            let args: Record<string, unknown>;
            try {
              args =
                typeof argsJson === "string"
                  ? (JSON.parse(argsJson) as Record<string, unknown>)
                  : ((argsJson as Record<string, unknown>) ?? {});
            } catch {
              const errorOutput = {
                type: "conversation.item.create",
                item: {
                  type: "function_call_output",
                  call_id: callId,
                  output: JSON.stringify({ success: false, error: "Invalid JSON arguments" }),
                },
              };
              dataChannel.send(JSON.stringify(errorOutput));
              dataChannel.send(JSON.stringify({ type: "response.create" }));
              return;
            }

            void executeToolCall(callId, toolName, args);
          } else if (data.type === "error") {
            setError(data.error?.message ?? "Unknown error");
          }

          // Capture transcript
          if (data.type === "conversation.item.input_audio_transcription.completed") {
            const userText = data.transcript as string;
            if (userText?.trim()) {
              transcriptRef.current.push({ role: "user", content: userText.trim() });
            }
          } else if (data.type === "response.audio_transcript.delta") {
            const delta = data.delta as string;
            if (delta) {
              currentAssistantTextRef.current += delta;
            }
          } else if (data.type === "response.audio_transcript.done") {
            if (currentAssistantTextRef.current.trim()) {
              transcriptRef.current.push({
                role: "assistant",
                content: currentAssistantTextRef.current.trim(),
              });
            }
            currentAssistantTextRef.current = "";
          }
        } catch {
          // Ignore parse errors
        }
      };

      dataChannel.onerror = () => {
        setError("Connection error");
        setStatus("error");
      };

      dataChannel.onclose = () => {
        setStatus("idle");
        setIsExpanded(false);
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "disconnected" || pc.connectionState === "failed") {
          cleanup();
          setStatus("idle");
          setIsExpanded(false);
        }
      };
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to start session");
      setStatus("error");
      cleanup();
    }
  }, [config, publicId, cleanup, setupAudioAnalysis, endSession]);

  // Auto-start session
  useEffect(() => {
    if (autostart && config && !autostartTriggeredRef.current) {
      autostartTriggeredRef.current = true;
      void startSession();
    }
  }, [autostart, config, startSession]);

  // Listen for start message from widget
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "ai-agent:start" && status === "idle" && config) {
        void startSession();
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [status, config, startSession]);

  // Toggle mute
  const toggleMute = useCallback(() => {
    const { audioStream } = webrtcRef.current;
    if (audioStream) {
      const newMuted = !isMuted;
      setIsMuted(newMuted);
      audioStream.getAudioTracks().forEach((track) => {
        track.enabled = !newMuted;
      });
    }
  }, [isMuted]);

  const positionClasses: Record<string, string> = {
    "bottom-right": "bottom-8 right-5",
    "bottom-left": "bottom-8 left-5",
    "top-right": "top-8 right-5",
    "top-left": "top-8 left-5",
  };

  const isDark = resolvedTheme === "dark";
  const primaryColor = config?.primary_color ?? "#6366f1";

  const getStateColor = () => {
    switch (agentState) {
      case "listening":
        return { color: "#22c55e", name: "Listening" };
      case "thinking":
        return { color: "#f59e0b", name: "Thinking" };
      case "speaking":
        return { color: "#3b82f6", name: "Speaking" };
      default:
        return { color: primaryColor, name: "Ready" };
    }
  };

  const stateInfo = getStateColor();

  if (error && !config) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-transparent">
        <div className="rounded-lg bg-red-50 p-4 text-red-600 shadow-lg">
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className={`fixed ${positionClasses[position] ?? positionClasses["bottom-right"]}`}>
        <div className="h-14 w-14 animate-pulse rounded-full bg-gray-200" />
      </div>
    );
  }

  return (
    <div
      className={`fixed ${positionClasses[position] ?? positionClasses["bottom-right"]} z-[9999] font-sans`}
    >
      {isExpanded ? (
        <div
          className="relative flex flex-col items-center gap-3 rounded-3xl p-6 transition-all duration-500"
          style={{
            backgroundColor: isDark ? "rgba(17, 24, 39, 0.95)" : "rgba(255, 255, 255, 0.95)",
            backdropFilter: "blur(20px)",
            boxShadow: `0 0 ${40 + smoothedLevel * 60}px ${smoothedLevel * 20}px ${stateInfo.color}40`,
          }}
        >
          {/* Circular Audio Visualizer */}
          <div className="relative flex h-32 w-32 items-center justify-center">
            {/* Outer glow ring */}
            <div
              className="absolute inset-0 rounded-full"
              style={{
                background: `radial-gradient(circle, ${stateInfo.color}20 0%, transparent 70%)`,
                transform: `scale(${1.2 + smoothedLevel * 0.5})`,
                transition: "transform 0.15s ease-out",
              }}
            />

            {/* Audio bars in a circle */}
            <div className="absolute inset-0">
              {frequencies.map((level, i) => {
                const angle = (i / BAR_COUNT) * 360;
                const barHeight = 8 + level * 32;
                const opacity = 0.3 + level * 0.7;

                return (
                  <div
                    key={i}
                    className="absolute left-1/2 top-1/2 origin-bottom"
                    style={{
                      width: "3px",
                      height: `${barHeight}px`,
                      backgroundColor: stateInfo.color,
                      opacity,
                      transform: `translate(-50%, -100%) rotate(${angle}deg) translateY(-28px)`,
                      borderRadius: "2px",
                      transition: "height 0.05s ease-out, opacity 0.05s ease-out",
                    }}
                  />
                );
              })}
            </div>

            {/* Center orb */}
            <div
              className="relative z-10 flex h-16 w-16 items-center justify-center rounded-full"
              style={{
                background: `linear-gradient(135deg, ${stateInfo.color} 0%, ${primaryColor} 100%)`,
                boxShadow: `0 0 ${20 + smoothedLevel * 30}px ${stateInfo.color}80`,
                transform: `scale(${1 + smoothedLevel * 0.15})`,
                transition: "transform 0.1s ease-out, box-shadow 0.1s ease-out",
              }}
            >
              <div
                className="absolute inset-2 rounded-full"
                style={{
                  background: `radial-gradient(circle, rgba(255,255,255,${0.3 + smoothedLevel * 0.4}) 0%, transparent 70%)`,
                }}
              />

              {status === "connecting" ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <Phone className="h-6 w-6 text-white" fill="white" />
              )}
            </div>

            {/* State indicator ring */}
            <div
              className="absolute inset-0 rounded-full border-2"
              style={{
                borderColor: stateInfo.color,
                opacity: 0.5 + smoothedLevel * 0.5,
                transform: `scale(${1.1 + smoothedLevel * 0.1})`,
                transition: "transform 0.15s ease-out, opacity 0.15s ease-out",
              }}
            />
          </div>

          {/* Agent name and status */}
          <div className="text-center">
            <p className="text-sm font-semibold" style={{ color: isDark ? "#ffffff" : "#1f2937" }}>
              {config.name}
            </p>
            <p className="text-xs font-medium" style={{ color: stateInfo.color }}>
              {status === "connecting" ? "Connecting..." : stateInfo.name}
            </p>
          </div>

          {/* Control buttons */}
          <div className="flex items-center gap-2">
            {status === "connected" && (
              <button
                onClick={toggleMute}
                className="rounded-full p-3 transition-all duration-200 hover:scale-105"
                style={{
                  backgroundColor: isMuted
                    ? "#ef4444"
                    : isDark
                      ? "rgba(255,255,255,0.1)"
                      : "rgba(0,0,0,0.05)",
                  color: isMuted ? "#ffffff" : isDark ? "#d1d5db" : "#4b5563",
                }}
              >
                {isMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
              </button>
            )}

            <button
              onClick={endSession}
              className="rounded-full bg-red-500 p-3 text-white transition-all duration-200 hover:scale-105 hover:bg-red-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {error && <p className="max-w-[200px] text-center text-xs text-red-500">{error}</p>}
        </div>
      ) : autostart ? (
        <div className="flex flex-col items-center justify-center gap-3 p-4">
          <div className="relative flex h-16 w-16 items-center justify-center">
            <div
              className="absolute inset-0 animate-spin rounded-full"
              style={{
                background: `conic-gradient(from 0deg, ${primaryColor} 0deg, transparent 120deg)`,
                animationDuration: "1s",
              }}
            />
            <div className="absolute inset-1 rounded-full bg-[#212121]" />
            <div
              className="absolute inset-3 rounded-full"
              style={{ backgroundColor: primaryColor, opacity: 0.3 }}
            />
          </div>
          <p className="text-sm font-medium text-gray-300">
            {status === "connecting" ? "Connecting..." : "Starting..."}
          </p>
          {error && <p className="max-w-[200px] text-center text-xs text-red-500">{error}</p>}
        </div>
      ) : (
        <button
          onClick={() => void startSession()}
          className="group relative flex items-center gap-3 overflow-hidden rounded-full py-3 pl-4 pr-6 shadow-lg transition-all duration-300 hover:scale-105 hover:shadow-xl active:scale-95"
          style={{
            backgroundColor: primaryColor,
            color: "#ffffff",
            boxShadow: `0 8px 32px ${primaryColor}50`,
          }}
        >
          <div
            className="absolute inset-0 opacity-30"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 50%, transparent 100%)",
              animation: "shimmer 2s infinite",
            }}
          />

          <div className="relative h-10 w-10">
            <div
              className="absolute inset-0 animate-spin rounded-full"
              style={{
                background:
                  "conic-gradient(from 0deg, rgba(255,255,255,0.8) 0deg, rgba(255,255,255,0.2) 90deg, rgba(255,255,255,0.8) 180deg, rgba(255,255,255,0.2) 270deg, rgba(255,255,255,0.8) 360deg)",
                animationDuration: "3s",
              }}
            />
            <div className="absolute inset-1 rounded-full" style={{ backgroundColor: primaryColor }} />
            <div className="absolute inset-2 rounded-full bg-white/50 transition-all duration-300 group-hover:bg-white/70" />
            <div
              className="absolute inset-0 animate-ping rounded-full opacity-20"
              style={{ backgroundColor: "white", animationDuration: "2s" }}
            />
          </div>

          <span className="relative z-10 text-sm font-semibold">{config.button_text}</span>
        </button>
      )}

      <style jsx>{`
        @keyframes shimmer {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(100%);
          }
        }
      `}</style>
    </div>
  );
}
