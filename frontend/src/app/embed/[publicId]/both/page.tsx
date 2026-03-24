"use client";

import { useEffect, useState, useCallback, useRef, use, Suspense } from "react";
import { Send, X, Mic, MicOff, MessageSquare, Loader2 } from "lucide-react";
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

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface BothEmbedPageProps {
  params: Promise<{ publicId: string }>;
}

function BothEmbedPageContent({ params }: BothEmbedPageProps) {
  const { publicId } = use(params);
  const searchParams = useSearchParams();
  const theme = (searchParams.get("theme") as "light" | "dark" | "auto") ?? "auto";
  const position = searchParams.get("position") ?? "bottom-right";
  const autostart = searchParams.get("autostart") === "true";

  // Shared state
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Voice state
  const [voiceStatus, setVoiceStatus] = useState<ConnectionStatus>("idle");
  const [agentState, setAgentState] = useState<AgentState>("idle");
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
  const currentAssistantTextRef = useRef<string>("");
  const currentAssistantMsgIdRef = useRef<string>("");
  const autostartTriggeredRef = useRef(false);

  // Theme resolution
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

  // Notify parent of state
  useEffect(() => {
    if (window.parent !== window) {
      const state = voiceStatus === "connected" ? agentState : isChatLoading ? "thinking" : "idle";
      window.parent.postMessage({ type: "ai-agent:state", state }, "*");
    }
  }, [agentState, isChatLoading, voiceStatus]);

  // Notify parent of audio level
  useEffect(() => {
    if (window.parent !== window && smoothedLevel > 0.05) {
      window.parent.postMessage({ type: "ai-agent:audio-level", level: smoothedLevel }, "*");
    }
  }, [smoothedLevel]);

  // Fetch config
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

        if (data.greeting_message) {
          setMessages([
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: data.greeting_message,
              timestamp: new Date(),
            },
          ]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load agent");
      }
    }
    if (publicId) {
      void fetchConfig();
    }
  }, [publicId]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  // Listen for start message from parent
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "ai-agent:start" && config) {
        if (voiceStatus === "idle") {
          void startVoiceSession();
        }
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceStatus, config]);

  // ───── Audio analysis ─────
  const setupAudioAnalysis = useCallback((stream: MediaStream) => {
    try {
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.7;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      audioRef.current = { audioContext, analyser, dataArray, animationFrame: null };

      const updateLevel = () => {
        if (audioRef.current.analyser && audioRef.current.dataArray) {
          audioRef.current.analyser.getByteFrequencyData(audioRef.current.dataArray);
          const data = audioRef.current.dataArray;

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

  const cleanupAudioAnalysis = useCallback(() => {
    if (audioRef.current.animationFrame) {
      cancelAnimationFrame(audioRef.current.animationFrame);
    }
    if (audioRef.current.audioContext) {
      try {
        void audioRef.current.audioContext.close();
      } catch {
        // Ignore
      }
    }
    audioRef.current = { audioContext: null, analyser: null, dataArray: null, animationFrame: null };
    setSmoothedLevel(0);
  }, []);

  // ───── Cleanup WebRTC ─────
  const cleanup = useCallback(() => {
    const { peerConnection, dataChannel, audioStream, audioElement } = webrtcRef.current;

    cleanupAudioAnalysis();

    if (dataChannel) {
      try { dataChannel.close(); } catch { /* ignore */ }
    }
    if (peerConnection) {
      try { peerConnection.close(); } catch { /* ignore */ }
    }
    if (audioStream) {
      try { audioStream.getTracks().forEach((track) => track.stop()); } catch { /* ignore */ }
    }
    if (audioElement) {
      try { audioElement.srcObject = null; audioElement.remove(); } catch { /* ignore */ }
    }

    webrtcRef.current = { peerConnection: null, dataChannel: null, audioStream: null, audioElement: null };
    setAgentState("idle");
  }, [cleanupAudioAnalysis]);

  useEffect(() => {
    return () => { cleanup(); };
  }, [cleanup]);

  // ───── End voice session ─────
  const endVoiceSession = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    cleanup();
    setVoiceStatus("idle");
  }, [cleanup]);

  // ───── Start voice session ─────
  const startVoiceSession = useCallback(async () => {
    if (!config) return;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    currentAssistantTextRef.current = "";
    currentAssistantMsgIdRef.current = "";

    setVoiceStatus("connecting");
    setError(null);
    setAgentState("idle");

    try {
      const tokenRes = await fetch(`/api/v1/p/embed/${publicId}/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: window.location.origin },
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

      webrtcRef.current = { peerConnection: pc, dataChannel, audioStream: micStream, audioElement };

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
        headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${ephemeralKey}` },
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
        setVoiceStatus("connected");
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

        dataChannel.send(JSON.stringify({ type: "session.update", session: sessionConfig }));

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

      // Tool call handler
      const executeToolCall = async (
        callId: string,
        toolName: string,
        args: Record<string, unknown>
      ) => {
        try {
          const toolResponse = await fetch(`/api/v1/p/embed/${publicId}/tool-call`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Origin: window.location.origin },
            body: JSON.stringify({ tool_name: toolName, arguments: args }),
          });

          const result = (await toolResponse.json()) as Record<string, unknown>;

          if (dataChannel.readyState === "open") {
            dataChannel.send(
              JSON.stringify({
                type: "conversation.item.create",
                item: { type: "function_call_output", call_id: callId, output: JSON.stringify(result) },
              })
            );
            dataChannel.send(JSON.stringify({ type: "response.create" }));
          }

          if (result.action === "end_call") {
            setTimeout(() => { endVoiceSession(); }, 3000);
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

          // Agent state transitions
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

          // Capture transcripts into chat messages
          if (data.type === "conversation.item.input_audio_transcription.completed") {
            const userText = data.transcript as string;
            if (userText?.trim()) {
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: "user",
                  content: userText.trim(),
                  timestamp: new Date(),
                },
              ]);
            }
          } else if (data.type === "response.audio_transcript.delta") {
            const delta = data.delta as string;
            if (delta) {
              currentAssistantTextRef.current += delta;
              const msgId = currentAssistantMsgIdRef.current;

              if (!msgId) {
                // Create a new assistant message
                const newId = crypto.randomUUID();
                currentAssistantMsgIdRef.current = newId;
                setMessages((prev) => [
                  ...prev,
                  {
                    id: newId,
                    role: "assistant",
                    content: currentAssistantTextRef.current,
                    timestamp: new Date(),
                  },
                ]);
              } else {
                // Update existing assistant message
                const text = currentAssistantTextRef.current;
                setMessages((prev) =>
                  prev.map((m) => (m.id === msgId ? { ...m, content: text } : m))
                );
              }
            }
          } else if (data.type === "response.audio_transcript.done") {
            // Finalize the assistant message
            if (currentAssistantTextRef.current.trim() && currentAssistantMsgIdRef.current) {
              const text = currentAssistantTextRef.current.trim();
              const msgId = currentAssistantMsgIdRef.current;
              setMessages((prev) =>
                prev.map((m) => (m.id === msgId ? { ...m, content: text } : m))
              );
            }
            currentAssistantTextRef.current = "";
            currentAssistantMsgIdRef.current = "";
          }
        } catch {
          // Ignore parse errors
        }
      };

      dataChannel.onerror = () => {
        setError("Connection error");
        setVoiceStatus("error");
      };

      dataChannel.onclose = () => {
        setVoiceStatus("idle");
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "disconnected" || pc.connectionState === "failed") {
          cleanup();
          setVoiceStatus("idle");
        }
      };
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to start voice session");
      setVoiceStatus("error");
      cleanup();
    }
  }, [config, publicId, cleanup, setupAudioAnalysis, endVoiceSession]);

  // Auto-start voice if requested
  useEffect(() => {
    if (autostart && config && !autostartTriggeredRef.current) {
      autostartTriggeredRef.current = true;
      void startVoiceSession();
    }
  }, [autostart, config, startVoiceSession]);

  // ───── Chat send ─────
  const sendMessage = useCallback(async () => {
    if (!inputValue.trim() || isChatLoading || !config) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsChatLoading(true);

    try {
      const conversationHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`/api/v1/p/embed/${publicId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: window.location.origin },
        body: JSON.stringify({
          message: userMessage.content,
          conversation_history: conversationHistory,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error((errData.detail as string) ?? "Failed to get response");
      }

      const data = await res.json();

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.response,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setIsChatLoading(false);
    }
  }, [inputValue, isChatLoading, config, messages, publicId]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const closeChat = () => {
    endVoiceSession();
    if (window.parent !== window) {
      window.parent.postMessage({ type: "ai-agent:close" }, "*");
    }
  };

  const toggleVoice = () => {
    if (voiceStatus === "connected" || voiceStatus === "connecting") {
      endVoiceSession();
    } else {
      void startVoiceSession();
    }
  };

  // ───── Derived values ─────
  const isDark = resolvedTheme === "dark";
  const primaryColor = config?.primary_color ?? "#6366f1";
  const voiceActive = voiceStatus === "connected" || voiceStatus === "connecting";

  const getStateColor = () => {
    switch (agentState) {
      case "listening":
        return "#22c55e";
      case "thinking":
        return "#f59e0b";
      case "speaking":
        return "#3b82f6";
      default:
        return primaryColor;
    }
  };

  const getStateLabel = () => {
    if (voiceStatus === "connecting") return "Connecting...";
    switch (agentState) {
      case "listening":
        return "Listening";
      case "thinking":
        return "Thinking";
      case "speaking":
        return "Speaking";
      default:
        return "Voice active";
    }
  };

  const positionClasses: Record<string, string> = {
    "bottom-right": "bottom-5 right-5",
    "bottom-left": "bottom-5 left-5",
    "top-right": "top-5 right-5",
    "top-left": "top-5 left-5",
  };

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
      <div
        className="flex h-[500px] w-[360px] flex-col overflow-hidden rounded-2xl shadow-2xl"
        style={{
          backgroundColor: isDark ? "#1f2937" : "#ffffff",
          border: isDark ? "1px solid #374151" : "1px solid #e5e7eb",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ backgroundColor: primaryColor }}
        >
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
              <MessageSquare className="h-4 w-4 text-white" />
            </div>
            <span className="font-semibold text-white">{config.name}</span>

            {/* Voice indicator in header */}
            {voiceActive && voiceStatus === "connected" && (
              <div className="flex items-center gap-1.5 rounded-full bg-white/20 px-2 py-0.5">
                <div
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor: getStateColor(),
                    boxShadow: `0 0 ${4 + smoothedLevel * 8}px ${getStateColor()}`,
                    transform: `scale(${1 + smoothedLevel * 0.5})`,
                    transition: "transform 0.1s ease-out, box-shadow 0.1s ease-out",
                  }}
                />
                <span className="text-[10px] font-medium text-white/90">{getStateLabel()}</span>
              </div>
            )}

            {voiceStatus === "connecting" && (
              <div className="flex items-center gap-1.5 rounded-full bg-white/20 px-2 py-0.5">
                <Loader2 className="h-3 w-3 animate-spin text-white/90" />
                <span className="text-[10px] font-medium text-white/90">Connecting...</span>
              </div>
            )}
          </div>
          <button
            onClick={closeChat}
            className="rounded-full p-1 transition-colors hover:bg-white/20"
          >
            <X className="h-5 w-5 text-white" />
          </button>
        </div>

        {/* Messages */}
        <div
          className="flex-1 overflow-y-auto p-4"
          style={{ backgroundColor: isDark ? "#111827" : "#f9fafb" }}
        >
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <p
                className="text-center text-sm"
                style={{ color: isDark ? "#9ca3af" : "#6b7280" }}
              >
                Start a conversation with {config.name}
              </p>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`mb-3 flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                  message.role === "user" ? "rounded-br-md" : "rounded-bl-md"
                }`}
                style={{
                  backgroundColor:
                    message.role === "user"
                      ? primaryColor
                      : isDark
                        ? "#374151"
                        : "#ffffff",
                  color:
                    message.role === "user"
                      ? "#ffffff"
                      : isDark
                        ? "#f3f4f6"
                        : "#1f2937",
                  boxShadow:
                    message.role === "assistant"
                      ? isDark
                        ? "0 1px 2px rgba(0,0,0,0.3)"
                        : "0 1px 2px rgba(0,0,0,0.1)"
                      : "none",
                }}
              >
                <p className="whitespace-pre-wrap text-sm">{message.content}</p>
              </div>
            </div>
          ))}

          {isChatLoading && (
            <div className="mb-3 flex justify-start">
              <div
                className="flex items-center gap-2 rounded-2xl rounded-bl-md px-4 py-2"
                style={{
                  backgroundColor: isDark ? "#374151" : "#ffffff",
                  boxShadow: isDark
                    ? "0 1px 2px rgba(0,0,0,0.3)"
                    : "0 1px 2px rgba(0,0,0,0.1)",
                }}
              >
                <div className="flex gap-1">
                  <div
                    className="h-2 w-2 animate-bounce rounded-full"
                    style={{ backgroundColor: primaryColor, animationDelay: "0ms" }}
                  />
                  <div
                    className="h-2 w-2 animate-bounce rounded-full"
                    style={{ backgroundColor: primaryColor, animationDelay: "150ms" }}
                  />
                  <div
                    className="h-2 w-2 animate-bounce rounded-full"
                    style={{ backgroundColor: primaryColor, animationDelay: "300ms" }}
                  />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div
          className="border-t p-3"
          style={{
            backgroundColor: isDark ? "#1f2937" : "#ffffff",
            borderColor: isDark ? "#374151" : "#e5e7eb",
          }}
        >
          {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={voiceActive ? "Voice active — or type here..." : "Type a message..."}
              disabled={isChatLoading}
              className="flex-1 rounded-full border px-4 py-2 text-sm outline-none transition-all focus:ring-2"
              style={{
                backgroundColor: isDark ? "#374151" : "#f3f4f6",
                borderColor: isDark ? "#4b5563" : "#e5e7eb",
                color: isDark ? "#f3f4f6" : "#1f2937",
              }}
            />
            <button
              onClick={() => void sendMessage()}
              disabled={!inputValue.trim() || isChatLoading}
              className="flex h-10 w-10 items-center justify-center rounded-full transition-all hover:scale-105 disabled:opacity-50"
              style={{ backgroundColor: primaryColor }}
            >
              {isChatLoading ? (
                <Loader2 className="h-5 w-5 animate-spin text-white" />
              ) : (
                <Send className="h-5 w-5 text-white" />
              )}
            </button>
            <button
              onClick={toggleVoice}
              disabled={voiceStatus === "connecting"}
              className="flex h-10 w-10 items-center justify-center rounded-full transition-all hover:scale-105 disabled:opacity-50"
              style={{
                backgroundColor: voiceActive
                  ? "#ef4444"
                  : isDark
                    ? "#374151"
                    : "#e5e7eb",
              }}
              title={voiceActive ? "Stop voice" : "Start voice"}
            >
              {voiceStatus === "connecting" ? (
                <Loader2 className="h-5 w-5 animate-spin" style={{ color: isDark ? "#d1d5db" : "#4b5563" }} />
              ) : voiceActive ? (
                <MicOff className="h-5 w-5 text-white" />
              ) : (
                <Mic className="h-5 w-5" style={{ color: isDark ? "#d1d5db" : "#4b5563" }} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BothEmbedPage({ params }: BothEmbedPageProps) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <BothEmbedPageContent params={params} />
    </Suspense>
  );
}
