import { apiGet, apiPost, apiPut } from "@/lib/api";
import type {
  HumanNudge,
  NudgeListResponse,
  NudgeStats,
  NudgeSettings,
  UpdateNudgeSettings,
  NudgeStatus,
  NudgeType,
  NudgePriority,
} from "@/types/nudge";

export interface NudgeListParams {
  page?: number;
  page_size?: number;
  status?: NudgeStatus;
  nudge_type?: NudgeType;
  priority?: NudgePriority;
  /** Only tasks tied to this contact (the contact detail "Next task" section). */
  contact_id?: number;
}

export interface CreateNudgeRequest {
  contact_id: number;
  title: string;
  message?: string;
  due_date: string;
  nudge_type?: NudgeType;
  priority?: NudgePriority;
  assigned_to_user_id?: number | null;
}

export interface UpdateNudgeRequest {
  title?: string;
  message?: string;
  due_date?: string;
  nudge_type?: NudgeType;
  priority?: NudgePriority;
  /** Explicit `null` unassigns; omit the field to leave the assignee as-is. */
  assigned_to_user_id?: number | null;
}

export const nudgesApi = {
  list: async (workspaceId: string, params: NudgeListParams = {}): Promise<NudgeListResponse> => {
    return apiGet<NudgeListResponse>(`/api/v1/workspaces/${workspaceId}/nudges`, { params });
  },

  getStats: async (workspaceId: string): Promise<NudgeStats> => {
    return apiGet<NudgeStats>(`/api/v1/workspaces/${workspaceId}/nudges/stats`);
  },

  act: async (workspaceId: string, nudgeId: string, actionTaken?: string): Promise<HumanNudge> => {
    return apiPut<HumanNudge>(
      `/api/v1/workspaces/${workspaceId}/nudges/${nudgeId}/act`,
      actionTaken ? { action_taken: actionTaken } : undefined,
    );
  },

  dismiss: async (workspaceId: string, nudgeId: string): Promise<HumanNudge> => {
    return apiPut<HumanNudge>(`/api/v1/workspaces/${workspaceId}/nudges/${nudgeId}/dismiss`);
  },

  snooze: async (
    workspaceId: string,
    nudgeId: string,
    snoozeUntil: string,
  ): Promise<HumanNudge> => {
    return apiPut<HumanNudge>(`/api/v1/workspaces/${workspaceId}/nudges/${nudgeId}/snooze`, {
      snooze_until: snoozeUntil,
    });
  },

  create: async (workspaceId: string, data: CreateNudgeRequest): Promise<HumanNudge> => {
    return apiPost<HumanNudge>(`/api/v1/workspaces/${workspaceId}/nudges`, data);
  },

  update: async (
    workspaceId: string,
    nudgeId: string,
    data: UpdateNudgeRequest,
  ): Promise<HumanNudge> => {
    return apiPut<HumanNudge>(`/api/v1/workspaces/${workspaceId}/nudges/${nudgeId}`, data);
  },

  getSettings: async (workspaceId: string): Promise<NudgeSettings> => {
    return apiGet<NudgeSettings>(`/api/v1/workspaces/${workspaceId}/nudge-settings`);
  },

  updateSettings: async (
    workspaceId: string,
    data: UpdateNudgeSettings,
  ): Promise<NudgeSettings> => {
    return apiPut<NudgeSettings>(`/api/v1/workspaces/${workspaceId}/nudge-settings`, data);
  },
};
