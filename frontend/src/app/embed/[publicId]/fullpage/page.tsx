"use client";

import { useEffect, useState, useCallback, useRef, use, Suspense } from "react";
import { Send, Mic, MicOff, Loader2, MessageSquare } from "lucide-react";
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

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
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

interface FullpageEmbedProps {
  params: Promise<{ publicId: string }>;
}

function FullpageEmbedContent({ params }: FullpageEmbedProps) {
  const { publicId } = use(params);
  const searchParams = useSearchParams();
  const theme = (searchParams.get("theme") as "light" | "dark" | "auto") ?? "auto";

  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Voice state
  const [voiceStatus, setVoiceStatus] = useState<ConnectionStatus>("idle");
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [isMuted, setIsMuted] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
  const transcriptRef = useRef<{ role: "user" | "assistant"; content: string }[]>([]);
  const currentAssistantTextRef = useRef<string>("");
  const sessionIdRef = useRef<string>("");
  const sessionStartTimeRef = useRef<number>(0);

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

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    if (config) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [config]);

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
  }, []);

  // Cleanup WebRTC
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

  // End voice session
  const endVoiceSession = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    void saveTranscript();
    cleanup();
    setVoiceStatus("idle");
  }, [cleanup, saveTranscript]);

  // Start voice session
  const startVoiceSession = useCallback(async () => {
    if (!config) return;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    transcriptRef.current = [];
    currentAssistantTextRef.current = "";
    sessionIdRef.current = crypto.randomUUID();
    sessionStartTimeRef.current = Date.now();

    setVoiceStatus("connecting");
    setError(null);
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
              endVoiceSession();
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

          // Capture transcripts and add as messages
          if (data.type === "conversation.item.input_audio_transcription.completed") {
            const userText = data.transcript as string;
            if (userText?.trim()) {
              transcriptRef.current.push({ role: "user", content: userText.trim() });
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
            }
          } else if (data.type === "response.audio_transcript.done") {
            if (currentAssistantTextRef.current.trim()) {
              const content = currentAssistantTextRef.current.trim();
              transcriptRef.current.push({ role: "assistant", content });
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content,
                  timestamp: new Date(),
                },
              ]);
            }
            currentAssistantTextRef.current = "";
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
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to start voice session");
      setVoiceStatus("error");
      cleanup();
    }
  }, [config, publicId, cleanup, endVoiceSession]);

  // Toggle mic
  const toggleMic = useCallback(() => {
    if (voiceStatus === "connected") {
      // Toggle mute
      const { audioStream } = webrtcRef.current;
      if (audioStream) {
        const newMuted = !isMuted;
        setIsMuted(newMuted);
        audioStream.getAudioTracks().forEach((track) => {
          track.enabled = !newMuted;
        });
      }
    } else if (voiceStatus === "idle") {
      // Start voice session
      void startVoiceSession();
    }
  }, [voiceStatus, isMuted, startVoiceSession]);

  // Send text message
  const sendMessage = useCallback(async () => {
    if (!inputValue.trim() || isLoading || !config) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      const conversationHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`/api/v1/p/embed/${publicId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: window.location.origin,
        },
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
      setIsLoading(false);
    }
  }, [inputValue, isLoading, config, messages, publicId]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const isDark = resolvedTheme === "dark";
  const primaryColor = config?.primary_color ?? "#6366f1";

  const voiceIsActive = voiceStatus === "connected" || voiceStatus === "connecting";

  const getVoiceStateInfo = () => {
    switch (agentState) {
      case "listening":
        return { color: "#22c55e", label: "Listening" };
      case "thinking":
        return { color: "#f59e0b", label: "Thinking" };
      case "speaking":
        return { color: "#3b82f6", label: "Speaking" };
      default:
        return { color: primaryColor, label: "Ready" };
    }
  };

  const stateInfo = getVoiceStateInfo();

  if (error && !config) {
    return (
      <div
        className="flex h-screen w-screen items-center justify-center"
        style={{ backgroundColor: isDark ? "#111827" : "#f9fafb" }}
      >
        <div className="rounded-lg bg-red-50 p-6 text-red-600 shadow-lg">
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div
        className="flex h-screen w-screen items-center justify-center"
        style={{ backgroundColor: isDark ? "#111827" : "#f9fafb" }}
      >
        <Loader2
          className="h-8 w-8 animate-spin"
          style={{ color: primaryColor }}
        />
      </div>
    );
  }

  return (
    <div
      className="flex h-screen w-screen flex-col font-sans"
      style={{
        backgroundColor: isDark ? "#111827" : "#f9fafb",
        color: isDark ? "#f3f4f6" : "#1f2937",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-center px-4 py-3"
        style={{
          backgroundColor: isDark ? "#1f2937" : "#ffffff",
          borderBottom: isDark ? "1px solid #374151" : "1px solid #e5e7eb",
          boxShadow: voiceIsActive
            ? `0 2px 12px ${stateInfo.color}40`
            : "0 1px 3px rgba(0,0,0,0.1)",
          transition: "box-shadow 0.3s ease",
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-full"
            style={{ backgroundColor: primaryColor }}
          >
            <MessageSquare className="h-4 w-4 text-white" />
          </div>
          <span
            className="font-semibold"
            style={{ color: isDark ? "#f3f4f6" : "#1f2937" }}
          >
            {config.name}
          </span>
          {voiceIsActive && (
            <div className="flex items-center gap-1.5">
              <div
                className="h-2 w-2 rounded-full"
                style={{
                  backgroundColor: voiceStatus === "connecting" ? "#f59e0b" : stateInfo.color,
                  boxShadow: `0 0 6px ${voiceStatus === "connecting" ? "#f59e0b" : stateInfo.color}`,
                  animation: voiceStatus === "connecting" ? "pulse 1.5s infinite" : undefined,
                }}
              />
              <span
                className="text-xs font-medium"
                style={{ color: voiceStatus === "connecting" ? "#f59e0b" : stateInfo.color }}
              >
                {voiceStatus === "connecting" ? "Connecting..." : stateInfo.label}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
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
              className={`max-w-[70%] rounded-2xl px-4 py-2 ${
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

        {isLoading && (
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

      {/* Input area */}
      <div
        className="border-t p-3"
        style={{
          backgroundColor: isDark ? "#1f2937" : "#ffffff",
          borderColor: isDark ? "#374151" : "#e5e7eb",
        }}
      >
        {error && (
          <p className="mb-2 text-xs text-red-500">{error}</p>
        )}
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type a message..."
            disabled={isLoading}
            className="flex-1 rounded-full border px-4 py-2 text-sm outline-none transition-all focus:ring-2"
            style={{
              backgroundColor: isDark ? "#374151" : "#f3f4f6",
              borderColor: isDark ? "#4b5563" : "#e5e7eb",
              color: isDark ? "#f3f4f6" : "#1f2937",
            }}
          />
          <button
            onClick={() => void sendMessage()}
            disabled={!inputValue.trim() || isLoading}
            className="flex h-10 w-10 items-center justify-center rounded-full transition-all hover:scale-105 disabled:opacity-50"
            style={{ backgroundColor: primaryColor }}
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-white" />
            ) : (
              <Send className="h-5 w-5 text-white" />
            )}
          </button>
          <button
            onClick={toggleMic}
            disabled={voiceStatus === "connecting"}
            className="flex h-10 w-10 items-center justify-center rounded-full transition-all hover:scale-105 disabled:opacity-50"
            style={{
              backgroundColor: voiceIsActive
                ? isMuted
                  ? "#ef4444"
                  : stateInfo.color
                : isDark
                  ? "#374151"
                  : "#e5e7eb",
              color: voiceIsActive ? "#ffffff" : isDark ? "#d1d5db" : "#4b5563",
            }}
            title={
              voiceIsActive
                ? isMuted
                  ? "Unmute microphone"
                  : "Mute microphone"
                : "Start voice"
            }
          >
            {voiceStatus === "connecting" ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : voiceIsActive && isMuted ? (
              <MicOff className="h-5 w-5" />
            ) : (
              <Mic className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

export default function FullpageEmbedPage({ params }: FullpageEmbedProps) {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen w-screen items-center justify-center bg-gray-50">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      }
    >
      <FullpageEmbedContent params={params} />
    </Suspense>
  );
}
