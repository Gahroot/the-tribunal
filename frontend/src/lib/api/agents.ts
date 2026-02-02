import api from "@/lib/api";

// Backend response types
export interface AgentResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  channel_mode: string;
  voice_provider: string;
  voice_id: string;
  language: string;
  system_prompt: string;
  temperature: number;
  text_response_delay_ms: number;
  text_max_context_messages: number;
  calcom_event_type_id: number | null;
  enabled_tools: string[];
  tool_settings: Record<string, string[]>;
  is_active: boolean;
  // IVR navigation settings
  enable_ivr_navigation: boolean;
  ivr_navigation_goal: string | null;
  ivr_loop_threshold: number;
  ivr_silence_duration_ms: number;
  ivr_post_dtmf_cooldown_ms: number;
  ivr_menu_buffer_silence_ms: number;
  created_at: string;
  updated_at: string;
}

export interface AgentsListParams {
  page?: number;
  page_size?: number;
  active_only?: boolean;
}

export interface AgentsListResponse {
  items: AgentResponse[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  channel_mode?: string;
  voice_provider?: string;
  voice_id?: string;
  language?: string;
  system_prompt: string;
  temperature?: number;
  text_response_delay_ms?: number;
  text_max_context_messages?: number;
  calcom_event_type_id?: number;
  enabled_tools?: string[];
  tool_settings?: Record<string, string[]>;
  // IVR navigation settings
  enable_ivr_navigation?: boolean;
  ivr_navigation_goal?: string;
  ivr_loop_threshold?: number;
  ivr_silence_duration_ms?: number;
  ivr_post_dtmf_cooldown_ms?: number;
  ivr_menu_buffer_silence_ms?: number;
}

export interface UpdateAgentRequest {
  name?: string;
  description?: string;
  channel_mode?: string;
  voice_provider?: string;
  voice_id?: string;
  language?: string;
  system_prompt?: string;
  temperature?: number;
  text_response_delay_ms?: number;
  text_max_context_messages?: number;
  calcom_event_type_id?: number;
  is_active?: boolean;
  enabled_tools?: string[];
  tool_settings?: Record<string, string[]>;
  // IVR navigation settings
  enable_ivr_navigation?: boolean;
  ivr_navigation_goal?: string;
  ivr_loop_threshold?: number;
  ivr_silence_duration_ms?: number;
  ivr_post_dtmf_cooldown_ms?: number;
  ivr_menu_buffer_silence_ms?: number;
}

// Embed settings types
export interface EmbedSettings {
  button_text: string;
  theme: string;
  position: string;
  primary_color: string;
  mode: string;
}

export interface EmbedSettingsResponse {
  public_id: string | null;
  embed_enabled: boolean;
  allowed_domains: string[];
  embed_settings: EmbedSettings;
  embed_code: string | null;
}

export interface EmbedSettingsUpdate {
  embed_enabled?: boolean;
  allowed_domains?: string[];
  embed_settings?: Partial<EmbedSettings>;
}

// Agents API
export const agentsApi = {
  list: async (workspaceId: string, params: AgentsListParams = {}): Promise<AgentsListResponse> => {
    const response = await api.get<AgentsListResponse>(
      `/api/v1/workspaces/${workspaceId}/agents`,
      { params }
    );
    return response.data;
  },

  get: async (workspaceId: string, agentId: string): Promise<AgentResponse> => {
    const response = await api.get<AgentResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}`
    );
    return response.data;
  },

  create: async (workspaceId: string, data: CreateAgentRequest): Promise<AgentResponse> => {
    const response = await api.post<AgentResponse>(
      `/api/v1/workspaces/${workspaceId}/agents`,
      data
    );
    return response.data;
  },

  update: async (
    workspaceId: string,
    agentId: string,
    data: UpdateAgentRequest
  ): Promise<AgentResponse> => {
    const response = await api.put<AgentResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, agentId: string): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/agents/${agentId}`);
  },

  getEmbedSettings: async (
    workspaceId: string,
    agentId: string
  ): Promise<EmbedSettingsResponse> => {
    const response = await api.get<EmbedSettingsResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/embed`
    );
    return response.data;
  },

  updateEmbedSettings: async (
    workspaceId: string,
    agentId: string,
    data: EmbedSettingsUpdate
  ): Promise<EmbedSettingsResponse> => {
    const response = await api.put<EmbedSettingsResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/embed`,
      data
    );
    return response.data;
  },
};
