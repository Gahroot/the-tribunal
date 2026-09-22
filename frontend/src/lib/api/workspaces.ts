import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";

export interface QuietHoursMandate {
  enabled: boolean;
  timezone: string;
  start: string;
  end: string;
}

export interface BatchPackMandate {
  pack_key: string;
  label: string;
  ad_count: number;
  price_cents: number;
}

export interface EscalationRuleMandate {
  key: string;
  label: string;
  keywords: string[];
}

export interface OperatorReportMandate {
  enabled: boolean;
  channel: "sms" | "push" | "email";
  phone: string | null;
  events: string[];
}

export interface AutonomyMandate {
  version: number;
  enabled: boolean;
  posture: "draft_and_wait" | "act_and_report";
  auto_send_first_touches: boolean;
  auto_close_batch_packs: boolean;
  default_offer_id: string | null;
  description?: string | null;
  batch_pack_anchor_key: string;
  batch_pack_max_price_cents: number;
  allowed_batch_packs: BatchPackMandate[];
  daily_send_cap: number;
  quiet_hours: QuietHoursMandate;
  escalation_rules: EscalationRuleMandate[];
  operator_report: OperatorReportMandate;
}

export interface WorkspaceResponse {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  settings: Record<string, unknown>;
  autonomy_mandate: AutonomyMandate;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceWithMembership {
  workspace: WorkspaceResponse;
  role: "owner" | "admin" | "member";
  is_default: boolean;
}

export interface CreateWorkspaceRequest {
  name: string;
  slug: string;
  description?: string;
  settings?: Record<string, unknown>;
}

export interface UpdateWorkspaceRequest {
  name?: string;
  description?: string;
  settings?: Record<string, unknown>;
}

export const workspacesApi = {
  list: async (): Promise<WorkspaceWithMembership[]> => {
    return apiGet<WorkspaceWithMembership[]>("/api/v1/workspaces");
  },

  get: async (workspaceId: string): Promise<WorkspaceResponse> => {
    return apiGet<WorkspaceResponse>(`/api/v1/workspaces/${workspaceId}`);
  },

  create: async (data: CreateWorkspaceRequest): Promise<WorkspaceResponse> => {
    return apiPost<WorkspaceResponse>("/api/v1/workspaces", data);
  },

  update: async (workspaceId: string, data: UpdateWorkspaceRequest): Promise<WorkspaceResponse> => {
    return apiPut<WorkspaceResponse>(`/api/v1/workspaces/${workspaceId}`, data);
  },

  getAutonomyMandate: async (workspaceId: string): Promise<AutonomyMandate> => {
    return apiGet<AutonomyMandate>(`/api/v1/workspaces/${workspaceId}/autonomy-mandate`);
  },

  updateAutonomyMandate: async (
    workspaceId: string,
    mandate: AutonomyMandate,
  ): Promise<AutonomyMandate> => {
    return apiPut<AutonomyMandate>(`/api/v1/workspaces/${workspaceId}/autonomy-mandate`, {
      mandate,
    });
  },

  delete: async (workspaceId: string): Promise<void> => {
    await apiDelete(`/api/v1/workspaces/${workspaceId}`);
  },

  setDefault: async (workspaceId: string): Promise<WorkspaceWithMembership> => {
    return apiPost<WorkspaceWithMembership>(`/api/v1/workspaces/${workspaceId}/set-default`);
  },

  updateMemberRole: async (
    workspaceId: string,
    userId: number,
    role: "admin" | "member",
  ): Promise<{ user_id: number; role: string; message: string }> => {
    return apiPut<{ user_id: number; role: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/members/${userId}/role`,
      { role },
    );
  },

  removeMember: async (workspaceId: string, userId: number): Promise<void> => {
    await apiDelete(`/api/v1/workspaces/${workspaceId}/members/${userId}`);
  },
};
