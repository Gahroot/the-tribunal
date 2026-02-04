import api from "@/lib/api";

// Backend response types
export interface PromptVersionResponse {
  id: string;
  agent_id: string;
  system_prompt: string;
  initial_greeting: string | null;
  temperature: number;
  version_number: number;
  change_summary: string | null;
  created_by_id: number | null;
  is_active: boolean;
  is_baseline: boolean;
  parent_version_id: string | null;
  total_calls: number;
  successful_calls: number;
  booked_appointments: number;
  // Multi-variant A/B testing fields
  traffic_percentage: number | null;
  experiment_id: string | null;
  arm_status: string;
  // Bandit statistics
  bandit_alpha: number;
  bandit_beta: number;
  total_reward: number;
  reward_count: number;
  created_at: string;
  activated_at: string | null;
}

export interface PromptVersionListResponse {
  items: PromptVersionResponse[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface PromptVersionStatsResponse {
  prompt_version_id: string;
  version_number: number;
  is_active: boolean;
  is_baseline: boolean;
  total_calls: number;
  completed_calls: number;
  failed_calls: number;
  appointments_booked: number;
  leads_qualified: number;
  booking_rate: number | null;
  qualification_rate: number | null;
  completion_rate: number | null;
  avg_duration_seconds: number | null;
  avg_quality_score: number | null;
  stats_from: string | null;
  stats_to: string | null;
}

export interface VersionComparisonItem {
  version_id: string;
  version_number: number;
  is_active: boolean;
  is_baseline: boolean;
  arm_status: string;
  probability_best: number;
  credible_interval_lower: number;
  credible_interval_upper: number;
  sample_size: number;
  booking_rate: number | null;
  mean_estimate: number;
}

export interface VersionComparisonResponse {
  versions: VersionComparisonItem[];
  winner_id: string | null;
  winner_probability: number | null;
  recommended_action: string;
  min_samples_needed: number;
}

export interface WinnerDetectionResponse {
  winner_id: string | null;
  winner_probability: number | null;
  confidence_threshold: number;
  is_conclusive: boolean;
  message: string;
}

export interface CreatePromptVersionRequest {
  system_prompt?: string;
  initial_greeting?: string;
  temperature?: number;
  change_summary?: string;
  is_baseline?: boolean;
  traffic_percentage?: number;
  experiment_id?: string;
}

export interface UpdatePromptVersionRequest {
  change_summary?: string;
  is_baseline?: boolean;
  traffic_percentage?: number;
  experiment_id?: string;
}

export interface PromptVersionListParams {
  page?: number;
  page_size?: number;
}

// Prompt Versions API
export const promptVersionsApi = {
  list: async (
    workspaceId: string,
    agentId: string,
    params: PromptVersionListParams = {}
  ): Promise<PromptVersionListResponse> => {
    const response = await api.get<PromptVersionListResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts`,
      { params }
    );
    return response.data;
  },

  getActive: async (
    workspaceId: string,
    agentId: string
  ): Promise<PromptVersionResponse[]> => {
    const response = await api.get<PromptVersionResponse[]>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/active`
    );
    return response.data;
  },

  get: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.get<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}`
    );
    return response.data;
  },

  create: async (
    workspaceId: string,
    agentId: string,
    data: CreatePromptVersionRequest
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts`,
      data
    );
    return response.data;
  },

  update: async (
    workspaceId: string,
    agentId: string,
    versionId: string,
    data: UpdatePromptVersionRequest
  ): Promise<PromptVersionResponse> => {
    const response = await api.put<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}`,
      data
    );
    return response.data;
  },

  activate: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<{ activated_version: PromptVersionResponse; deactivated_version_id: string | null }> => {
    const response = await api.post<{
      activated_version: PromptVersionResponse;
      deactivated_version_id: string | null;
    }>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/activate`
    );
    return response.data;
  },

  activateForTesting: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/activate-for-testing`
    );
    return response.data;
  },

  deactivate: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/deactivate`
    );
    return response.data;
  },

  pause: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/pause`
    );
    return response.data;
  },

  resume: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/resume`
    );
    return response.data;
  },

  eliminate: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<PromptVersionResponse> => {
    const response = await api.post<PromptVersionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/eliminate`
    );
    return response.data;
  },

  rollback: async (
    workspaceId: string,
    agentId: string,
    versionId: string
  ): Promise<{ new_version: PromptVersionResponse; rolled_back_from: string }> => {
    const response = await api.post<{
      new_version: PromptVersionResponse;
      rolled_back_from: string;
    }>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/rollback`
    );
    return response.data;
  },

  getStats: async (
    workspaceId: string,
    agentId: string,
    versionId: string,
    days: number = 30
  ): Promise<PromptVersionStatsResponse> => {
    const response = await api.get<PromptVersionStatsResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/${versionId}/stats`,
      { params: { days } }
    );
    return response.data;
  },

  compare: async (
    workspaceId: string,
    agentId: string,
    winnerThreshold: number = 0.95
  ): Promise<VersionComparisonResponse> => {
    const response = await api.get<VersionComparisonResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/compare`,
      { params: { winner_threshold: winnerThreshold } }
    );
    return response.data;
  },

  detectWinner: async (
    workspaceId: string,
    agentId: string,
    threshold: number = 0.95
  ): Promise<WinnerDetectionResponse> => {
    const response = await api.get<WinnerDetectionResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/prompts/winner`,
      { params: { threshold } }
    );
    return response.data;
  },
};
