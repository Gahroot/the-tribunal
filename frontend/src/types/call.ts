// Call record types

export interface CallRecord {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  channel: string;
  status: "initiated" | "ringing" | "in_progress" | "completed" | "failed" | "busy" | "no_answer";
  from_number?: string;
  to_number?: string;
  contact_name?: string;
  contact_id?: number;
  duration_seconds?: number;
  recording_url?: string;
  transcript?: string;
  agent_id?: string;
  agent_name?: string;
  is_ai?: boolean;
  booking_outcome?: string;
  created_at: string;
  // Optional fields for active calls
  started_at?: string;
  answered_at?: string;
  ended_at?: string;
}
