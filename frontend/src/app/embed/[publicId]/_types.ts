export interface AgentConfig {
  public_id: string;
  name: string;
  greeting_message: string | null;
  button_text: string;
  theme: "light" | "dark" | "auto";
  position: string;
  primary_color: string;
  language: string;
  voice?: string;
  channel_mode: string;
}

export interface TokenResponse {
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

export type ConnectionStatus = "idle" | "connecting" | "connected" | "error";
export type AgentState = "idle" | "listening" | "thinking" | "speaking";

export type WebRTCResources = {
  peerConnection: RTCPeerConnection | null;
  dataChannel: RTCDataChannel | null;
  audioStream: MediaStream | null;
  audioElement: HTMLAudioElement | null;
};

export type AudioResources = {
  audioContext: AudioContext | null;
  analyser: AnalyserNode | null;
  dataArray: Uint8Array<ArrayBuffer> | null;
  animationFrame: number | null;
};

export type TranscriptEntry = {
  role: "user" | "assistant";
  content: string;
};

export type ThemeOption = "light" | "dark" | "auto";

export type ResolvedTheme = "light" | "dark";

export const POSITION_CLASSES: Record<string, string> = {
  "bottom-right": "bottom-5 right-5",
  "bottom-left": "bottom-5 left-5",
  "top-right": "top-5 right-5",
  "top-left": "top-5 left-5",
};

export const POSITION_CLASSES_LG: Record<string, string> = {
  "bottom-right": "bottom-8 right-5",
  "bottom-left": "bottom-8 left-5",
  "top-right": "top-8 right-5",
  "top-left": "top-8 left-5",
};
