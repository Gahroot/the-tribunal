import { api } from "@/lib/api";

export interface LeadSource {
  id: string;
  workspace_id: string;
  name: string;
  public_key: string;
  allowed_domains: string[];
  enabled: boolean;
  action: "collect" | "auto_text" | "auto_call" | "enroll_campaign";
  action_config: Record<string, string>;
  created_at: string;
  updated_at: string;
  endpoint_url: string;
}

export interface LeadSourceCreateRequest {
  name: string;
  allowed_domains: string[];
  action: "collect" | "auto_text" | "auto_call" | "enroll_campaign";
  action_config?: Record<string, string>;
}

export interface LeadSourceUpdateRequest {
  name?: string;
  allowed_domains?: string[];
  enabled?: boolean;
  action?: "collect" | "auto_text" | "auto_call" | "enroll_campaign";
  action_config?: Record<string, string>;
}

export const leadSourcesApi = {
  list: async (workspaceId: string): Promise<LeadSource[]> => {
    const response = await api.get<LeadSource[]>(
      `/api/v1/workspaces/${workspaceId}/lead-sources`
    );
    return response.data;
  },

  get: async (workspaceId: string, id: string): Promise<LeadSource> => {
    const response = await api.get<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources/${id}`
    );
    return response.data;
  },

  create: async (
    workspaceId: string,
    data: LeadSourceCreateRequest
  ): Promise<LeadSource> => {
    const response = await api.post<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources`,
      data
    );
    return response.data;
  },

  update: async (
    workspaceId: string,
    id: string,
    data: LeadSourceUpdateRequest
  ): Promise<LeadSource> => {
    const response = await api.put<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources/${id}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, id: string): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/lead-sources/${id}`);
  },
};
