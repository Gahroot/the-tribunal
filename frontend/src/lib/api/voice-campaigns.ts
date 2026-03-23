import { apiGet, apiPost } from "@/lib/api";
import type {
  VoiceCampaign,
  VoiceCampaignContact,
  VoiceCampaignAnalytics,
  CampaignStatus,
  GuaranteeProgress,
} from "@/types";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";

// Request Types
export interface CreateVoiceCampaignRequest {
  name: string;
  description?: string;
  from_phone_number: string;

  // Voice settings
  voice_agent_id: string;
  voice_connection_id?: string;
  enable_machine_detection?: boolean;
  max_call_duration_seconds?: number;

  // SMS fallback settings
  sms_fallback_enabled?: boolean;
  sms_fallback_template?: string;
  sms_fallback_use_ai?: boolean;
  sms_fallback_agent_id?: string;

  // AI settings
  ai_enabled?: boolean;
  qualification_criteria?: string;

  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone?: string;
  calls_per_minute?: number;
}

export interface UpdateVoiceCampaignRequest {
  name?: string;
  description?: string;

  // Voice settings
  voice_agent_id?: string;
  voice_connection_id?: string;
  enable_machine_detection?: boolean;
  max_call_duration_seconds?: number;

  // SMS fallback settings
  sms_fallback_enabled?: boolean;
  sms_fallback_template?: string;
  sms_fallback_use_ai?: boolean;
  sms_fallback_agent_id?: string;

  // AI settings
  ai_enabled?: boolean;
  qualification_criteria?: string;

  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone?: string;
  calls_per_minute?: number;
}

export interface VoiceCampaignsListParams {
  page?: number;
  page_size?: number;
  status_filter?: CampaignStatus;
}

export interface AddContactsRequest {
  contact_ids: number[];
}

export interface VoiceCampaignContactsListParams {
  status_filter?: string;
  limit?: number;
}

const baseApi = createApiClient<VoiceCampaign, CreateVoiceCampaignRequest, UpdateVoiceCampaignRequest>({
  resourcePath: "voice-campaigns",
}) as FullApiClient<VoiceCampaign, CreateVoiceCampaignRequest, UpdateVoiceCampaignRequest>;

// Voice Campaigns API
export const voiceCampaignsApi = {
  ...baseApi,

  // Override list — backend returns plain VoiceCampaign[], not PaginatedResponse
  list: async (
    workspaceId: string,
    params: VoiceCampaignsListParams = {}
  ): Promise<VoiceCampaign[]> => {
    return apiGet<VoiceCampaign[]>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns`,
      { params }
    );
  },

  // Start a voice campaign
  start: async (
    workspaceId: string,
    id: string
  ): Promise<{ status: string; message: string }> => {
    return apiPost<{ status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${id}/start`
    );
  },

  // Pause a voice campaign
  pause: async (
    workspaceId: string,
    id: string
  ): Promise<{ status: string }> => {
    return apiPost<{ status: string }>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${id}/pause`
    );
  },

  // Resume a voice campaign
  resume: async (
    workspaceId: string,
    id: string
  ): Promise<{ status: string }> => {
    return apiPost<{ status: string }>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${id}/resume`
    );
  },

  // Cancel a voice campaign
  cancel: async (
    workspaceId: string,
    id: string
  ): Promise<{ status: string }> => {
    return apiPost<{ status: string }>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${id}/cancel`
    );
  },

  // Add contacts to a voice campaign
  addContacts: async (
    workspaceId: string,
    campaignId: string,
    data: AddContactsRequest
  ): Promise<{ added: number }> => {
    return apiPost<{ added: number }>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${campaignId}/contacts`,
      data
    );
  },

  // List contacts in a voice campaign
  listContacts: async (
    workspaceId: string,
    campaignId: string,
    params: VoiceCampaignContactsListParams = {}
  ): Promise<VoiceCampaignContact[]> => {
    return apiGet<VoiceCampaignContact[]>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${campaignId}/contacts`,
      { params }
    );
  },

  // Get voice campaign analytics
  getAnalytics: async (
    workspaceId: string,
    campaignId: string
  ): Promise<VoiceCampaignAnalytics> => {
    return apiGet<VoiceCampaignAnalytics>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${campaignId}/analytics`
    );
  },

  // Get voice campaign guarantee progress
  getGuaranteeProgress: async (workspaceId: string, campaignId: string): Promise<GuaranteeProgress> => {
    return apiGet<GuaranteeProgress>(
      `/api/v1/workspaces/${workspaceId}/voice-campaigns/${campaignId}/guarantee`
    );
  },
};
