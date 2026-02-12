import api from "@/lib/api";
import { createApiClient } from "@/lib/api/create-api-client";

// Backend response types
export interface ImprovementSuggestionResponse {
  id: string;
  agent_id: string;
  source_version_id: string;
  suggested_prompt: string;
  suggested_greeting: string | null;
  mutation_type: string;
  analysis_summary: string;
  expected_improvement: string | null;
  status: string;
  reviewed_at: string | null;
  reviewed_by_id: number | null;
  rejection_reason: string | null;
  created_version_id: string | null;
  created_at: string;
}

export interface ImprovementSuggestionListResponse {
  items: ImprovementSuggestionResponse[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SuggestionListParams {
  agent_id?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

export interface ApproveResponse {
  suggestion: ImprovementSuggestionResponse;
  created_version_id: string;
}

export interface GenerateSuggestionsRequest {
  num_suggestions?: number;
}

// Create base API client with standard CRUD methods (list, get only)
const baseApi = createApiClient<ImprovementSuggestionResponse, never, never>({
  resourcePath: "suggestions",
  includeCreate: false,
  includeUpdate: false,
  includeDelete: false,
});

// Type assertion to ensure get is non-optional since we enabled it
const baseApiWithGet = baseApi as {
  list: typeof baseApi.list;
  get: NonNullable<typeof baseApi.get>;
};

// Improvement Suggestions API
export const improvementSuggestionsApi = {
  ...baseApiWithGet,

  getPendingCount: async (workspaceId: string): Promise<{ pending_count: number }> => {
    const response = await api.get<{ pending_count: number }>(
      `/api/v1/workspaces/${workspaceId}/suggestions/pending-count`
    );
    return response.data;
  },

  approve: async (
    workspaceId: string,
    suggestionId: string,
    activate: boolean = true
  ): Promise<ApproveResponse> => {
    const response = await api.post<ApproveResponse>(
      `/api/v1/workspaces/${workspaceId}/suggestions/${suggestionId}/approve`,
      null,
      { params: { activate } }
    );
    return response.data;
  },

  reject: async (
    workspaceId: string,
    suggestionId: string,
    reason?: string
  ): Promise<ImprovementSuggestionResponse> => {
    const response = await api.post<ImprovementSuggestionResponse>(
      `/api/v1/workspaces/${workspaceId}/suggestions/${suggestionId}/reject`,
      { reason }
    );
    return response.data;
  },

  getStats: async (
    workspaceId: string
  ): Promise<{ approved_count: number; rejected_count: number; auto_generated_count: number }> => {
    const response = await api.get<{ approved_count: number; rejected_count: number; auto_generated_count: number }>(
      `/api/v1/workspaces/${workspaceId}/suggestions/stats`
    );
    return response.data;
  },

  generateForAgent: async (
    workspaceId: string,
    agentId: string,
    numSuggestions: number = 3
  ): Promise<ImprovementSuggestionResponse[]> => {
    const response = await api.post<ImprovementSuggestionResponse[]>(
      `/api/v1/workspaces/${workspaceId}/suggestions/agents/${agentId}/generate`,
      { num_suggestions: numSuggestions }
    );
    return response.data;
  },
};
