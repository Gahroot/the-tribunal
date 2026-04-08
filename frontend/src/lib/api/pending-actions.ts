import { apiGet, apiPost } from "@/lib/api";
import type {
  PendingAction,
  PendingActionListResponse,
  PendingActionStats,
  PendingActionStatus,
} from "@/types/pending-action";

export interface PendingActionListParams {
  page?: number;
  page_size?: number;
  status?: PendingActionStatus;
}

export const pendingActionsApi = {
  list: async (
    workspaceId: string,
    params: PendingActionListParams = {}
  ): Promise<PendingActionListResponse> => {
    return apiGet<PendingActionListResponse>(
      `/api/v1/workspaces/${workspaceId}/pending-actions`,
      { params }
    );
  },

  getStats: async (workspaceId: string): Promise<PendingActionStats> => {
    return apiGet<PendingActionStats>(
      `/api/v1/workspaces/${workspaceId}/pending-actions/stats`
    );
  },

  get: async (workspaceId: string, actionId: string): Promise<PendingAction> => {
    return apiGet<PendingAction>(
      `/api/v1/workspaces/${workspaceId}/pending-actions/${actionId}`
    );
  },

  approve: async (workspaceId: string, actionId: string): Promise<PendingAction> => {
    return apiPost<PendingAction>(
      `/api/v1/workspaces/${workspaceId}/pending-actions/${actionId}/approve`
    );
  },

  reject: async (
    workspaceId: string,
    actionId: string,
    reason?: string
  ): Promise<PendingAction> => {
    return apiPost<PendingAction>(
      `/api/v1/workspaces/${workspaceId}/pending-actions/${actionId}/reject`,
      reason ? { reason } : undefined
    );
  },
};
