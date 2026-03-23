import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";

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
    return apiGet<LeadSource[]>(
      `/api/v1/workspaces/${workspaceId}/lead-sources`
    );
  },

  get: async (workspaceId: string, id: string): Promise<LeadSource> => {
    return apiGet<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources/${id}`
    );
  },

  create: async (
    workspaceId: string,
    data: LeadSourceCreateRequest
  ): Promise<LeadSource> => {
    return apiPost<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources`,
      data
    );
  },

  update: async (
    workspaceId: string,
    id: string,
    data: LeadSourceUpdateRequest
  ): Promise<LeadSource> => {
    return apiPut<LeadSource>(
      `/api/v1/workspaces/${workspaceId}/lead-sources/${id}`,
      data
    );
  },

  delete: async (workspaceId: string, id: string): Promise<void> => {
    await apiDelete(`/api/v1/workspaces/${workspaceId}/lead-sources/${id}`);
  },
};
