// OpenAI Realtime Voice Types

export type RealtimeSessionStatus = "connecting" | "connected" | "active" | "disconnected" | "error";

export interface RealtimeSession {
  id: string;
  call_id: string;
  contact_id: number;
  agent_id: string;
  status: RealtimeSessionStatus;
  model: string;
  voice: string;
  // Audio settings
  input_audio_format: "pcm16" | "g711_ulaw" | "g711_alaw";
  output_audio_format: "pcm16" | "g711_ulaw" | "g711_alaw";
  // Turn detection
  turn_detection_type: "server_vad" | "none";
  turn_detection_threshold?: number;
  turn_detection_silence_ms?: number;
  // Conversation state
  conversation_items: RealtimeConversationItem[];
  // Timestamps
  started_at: string;
  ended_at?: string;
}

export interface RealtimeConversationItem {
  id: string;
  type: "message" | "function_call" | "function_call_output";
  role: "user" | "assistant" | "system";
  content: RealtimeContentPart[];
  status: "in_progress" | "completed" | "cancelled";
  created_at: string;
}

export interface RealtimeContentPart {
  type: "input_text" | "input_audio" | "text" | "audio";
  text?: string;
  audio?: string; // Base64 encoded audio
  transcript?: string;
}

export interface RealtimeEvent {
  type: string;
  event_id: string;
  // Session events
  session?: Partial<RealtimeSession>;
  // Conversation events
  item?: RealtimeConversationItem;
  // Audio events
  audio?: string;
  // Error events
  error?: {
    type: string;
    code: string;
    message: string;
  };
}
