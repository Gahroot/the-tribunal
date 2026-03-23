import { apiGet, apiPost } from "@/lib/api";
import type { CallRecord } from "@/types";

export interface CallsListParams {
  page?: number;
  page_size?: number;
  direction?: "inbound" | "outbound";
  status?: string;
  search?: string;
}

export interface InitiateCallRequest {
  to_number: string;
  from_phone_number: string;
  contact_phone?: string;
  agent_id?: string;
}

export interface InitiateCallResponse {
  id: string;
  conversation_id: string;
  direction: string;
  channel: string;
  status: string;
  duration_seconds: number | null;
  recording_url: string | null;
  transcript: string | null;
  created_at: string;
}

export interface CallsListResponse {
  items: CallRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  completed_count: number;
  total_duration_seconds: number;
}

export interface CallStatsResponse {
  total_calls: number;
  completed_calls: number;
  inbound_calls: number;
  outbound_calls: number;
  total_duration_seconds: number;
  average_duration_seconds: number;
}

export const callsApi = {
  list: async (workspaceId: string, params: CallsListParams = {}): Promise<CallsListResponse> => {
    return apiGet<CallsListResponse>(
      `/api/v1/workspaces/${workspaceId}/calls`,
      { params }
    );
  },

  get: async (workspaceId: string, id: string): Promise<CallRecord> => {
    return apiGet<CallRecord>(
      `/api/v1/workspaces/${workspaceId}/calls/${id}`
    );
  },

  initiate: async (
    workspaceId: string,
    data: InitiateCallRequest
  ): Promise<InitiateCallResponse> => {
    return apiPost<InitiateCallResponse>(
      `/api/v1/workspaces/${workspaceId}/calls`,
      data
    );
  },

  hangup: async (workspaceId: string, callId: string): Promise<{ success: boolean }> => {
    return apiPost<{ success: boolean }>(
      `/api/v1/workspaces/${workspaceId}/calls/${callId}/hangup`
    );
  },
};
