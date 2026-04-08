import { apiGet, apiPut, apiPatch, apiDelete } from "@/lib/api";
import type {
  HumanProfile,
  HumanProfileCreate,
  HumanProfileUpdate,
} from "@/types/human-profile";

export const humanProfilesApi = {
  get: async (workspaceId: string, agentId: string): Promise<HumanProfile> => {
    return apiGet<HumanProfile>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/human-profile`
    );
  },

  upsert: async (
    workspaceId: string,
    agentId: string,
    data: HumanProfileCreate
  ): Promise<HumanProfile> => {
    return apiPut<HumanProfile>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/human-profile`,
      data
    );
  },

  update: async (
    workspaceId: string,
    agentId: string,
    data: HumanProfileUpdate
  ): Promise<HumanProfile> => {
    return apiPatch<HumanProfile>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/human-profile`,
      data
    );
  },

  remove: async (workspaceId: string, agentId: string): Promise<void> => {
    return apiDelete(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/human-profile`
    );
  },
};
