import api from "@/lib/api";
import type {
  Campaign,
  CampaignContact,
  CampaignStatus,
  CampaignType,
  CampaignContactStatus,
  GuaranteeProgress,
} from "@/types";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";

// Request/Response Types
export interface CampaignsListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: CampaignStatus;
  type?: CampaignType;
}

export interface CampaignsListResponse {
  items: Campaign[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateCampaignRequest {
  name: string;
  description?: string;
  type: CampaignType;
  sms_template?: string;
  email_subject?: string;
  email_template?: string;
  voice_script?: string;
  agent_id?: string;
  scheduled_start?: string;
  scheduled_end?: string;
  messages_per_hour?: number;
  max_retries?: number;
  retry_delay_minutes?: number;
}

export interface UpdateCampaignRequest {
  name?: string;
  description?: string;
  type?: CampaignType;
  status?: CampaignStatus;
  sms_template?: string;
  email_subject?: string;
  email_template?: string;
  voice_script?: string;
  agent_id?: string;
  scheduled_start?: string;
  scheduled_end?: string;
  messages_per_hour?: number;
  max_retries?: number;
  retry_delay_minutes?: number;
}

export interface CampaignContactsListParams {
  page?: number;
  page_size?: number;
  status?: CampaignContactStatus;
}

export interface CampaignContactsListResponse {
  contacts: CampaignContact[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AddContactsToCampaignRequest {
  contact_ids: number[];
  personalization_data?: Record<number, Record<string, unknown>>;
}

export interface CampaignAnalytics {
  total_contacts: number;
  messages_sent: number;
  messages_delivered: number;
  messages_failed: number;
  replies_received: number;
  contacts_qualified: number;
  contacts_opted_out: number;
  reply_rate: number;
  qualification_rate: number;
}

export interface CampaignActionResponse {
  success: boolean;
  message: string;
  campaign: Campaign;
}

const baseApi = createApiClient<Campaign, CreateCampaignRequest, UpdateCampaignRequest>({
  resourcePath: "campaigns",
}) as FullApiClient<Campaign, CreateCampaignRequest, UpdateCampaignRequest>;

// Campaign CRUD API
export const campaignsApi = {
  ...baseApi,

  // Get campaign analytics (computed rates)
  getAnalytics: async (workspaceId: string, id: string): Promise<CampaignAnalytics> => {
    const response = await api.get<CampaignAnalytics>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/analytics`
    );
    return response.data;
  },

  // Campaign lifecycle actions
  start: async (workspaceId: string, id: string): Promise<CampaignActionResponse> => {
    const response = await api.post<CampaignActionResponse>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/start`
    );
    return response.data;
  },

  pause: async (workspaceId: string, id: string): Promise<CampaignActionResponse> => {
    const response = await api.post<CampaignActionResponse>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/pause`
    );
    return response.data;
  },

  resume: async (workspaceId: string, id: string): Promise<CampaignActionResponse> => {
    const response = await api.post<CampaignActionResponse>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/resume`
    );
    return response.data;
  },

  cancel: async (workspaceId: string, id: string): Promise<CampaignActionResponse> => {
    const response = await api.post<CampaignActionResponse>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/cancel`
    );
    return response.data;
  },

  // Duplicate a campaign
  duplicate: async (workspaceId: string, id: string, name?: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${id}/duplicate`,
      { name }
    );
    return response.data;
  },

  // Get campaign guarantee progress
  getGuaranteeProgress: async (workspaceId: string, campaignId: string): Promise<GuaranteeProgress> => {
    const response = await api.get<GuaranteeProgress>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/guarantee`
    );
    return response.data;
  },
};

// Campaign Contacts API
export const campaignContactsApi = {
  // List contacts in a campaign
  list: async (
    workspaceId: string,
    campaignId: string,
    params: CampaignContactsListParams = {}
  ): Promise<CampaignContactsListResponse> => {
    const response = await api.get<CampaignContactsListResponse>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts`,
      { params }
    );
    return response.data;
  },

  // Add contacts to a campaign
  add: async (
    workspaceId: string,
    campaignId: string,
    data: AddContactsToCampaignRequest
  ): Promise<{ added: number; skipped: number }> => {
    const response = await api.post<{ added: number; skipped: number }>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts`,
      data
    );
    return response.data;
  },

  // Remove a contact from a campaign
  remove: async (workspaceId: string, campaignId: string, contactId: number): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/${contactId}`);
  },

  // Remove multiple contacts from a campaign
  removeBulk: async (workspaceId: string, campaignId: string, contactIds: number[]): Promise<{ removed: number }> => {
    const response = await api.post<{ removed: number }>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/remove`,
      { contact_ids: contactIds }
    );
    return response.data;
  },

  // Get a specific campaign contact
  get: async (workspaceId: string, campaignId: string, contactId: number): Promise<CampaignContact> => {
    const response = await api.get<CampaignContact>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/${contactId}`
    );
    return response.data;
  },

  // Update personalization data for a campaign contact
  updatePersonalization: async (
    workspaceId: string,
    campaignId: string,
    contactId: number,
    personalizationData: Record<string, unknown>
  ): Promise<CampaignContact> => {
    const response = await api.patch<CampaignContact>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/${contactId}`,
      { personalization_data: personalizationData }
    );
    return response.data;
  },

  // Retry failed contacts
  retryFailed: async (workspaceId: string, campaignId: string): Promise<{ queued: number }> => {
    const response = await api.post<{ queued: number }>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/retry-failed`
    );
    return response.data;
  },

  // Skip specific contacts
  skip: async (workspaceId: string, campaignId: string, contactIds: number[]): Promise<{ skipped: number }> => {
    const response = await api.post<{ skipped: number }>(
      `/api/v1/workspaces/${workspaceId}/campaigns/${campaignId}/contacts/skip`,
      { contact_ids: contactIds }
    );
    return response.data;
  },
};
