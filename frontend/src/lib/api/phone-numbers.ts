import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { Schemas } from "@/lib/api/_client";
import { createApiClient } from "@/lib/api/create-api-client";
import type { PhoneNumber } from "@/types";

// Request/Response Types
export interface PhoneNumbersListParams {
  page?: number;
  page_size?: number;
  sms_enabled?: boolean;
  voice_enabled?: boolean;
  active_only?: boolean;
  [key: string]: unknown;
}

export interface PhoneNumbersListResponse {
  items: PhoneNumber[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SearchPhoneNumbersRequest {
  country: string;
  area_code?: string;
  contains?: string;
  limit?: number;
}

export interface PhoneNumberSearchResult {
  id: string;
  phone_number: string;
  friendly_name: string | null;
  capabilities: {
    sms?: boolean;
    voice?: boolean;
    mms?: boolean;
  } | null;
}

export interface PurchasePhoneNumberRequest {
  phone_number: string;
  /** Agent that answers inbound calls. Omit to let the server pick the only eligible voice agent. */
  assigned_agent_id?: string | null;
  /** Keep the number SMS-only with no inbound agent. */
  skip_agent_assignment?: boolean;
}

export type PhoneNumberInboundReadiness = Schemas["PhoneNumberInboundReadinessResponse"];
export type PhoneNumbersInboundReadiness = Schemas["PhoneNumbersInboundReadinessResponse"];
export type EligibleVoiceAgent = Schemas["EligibleVoiceAgentResponse"];
export type PhoneNumberPurchaseResult = Schemas["PhoneNumberPurchaseResponse"];

export interface PhoneNumberTelephonyStatus {
  enabled: boolean;
  provider: "telnyx";
  message: string;
  action_label?: string | null;
  action_href?: string | null;
}

// Create base API client with standard methods (list, get only - no create/update)
// Note: release uses a different endpoint and return type than standard delete
const basePhoneNumbersApi = createApiClient<PhoneNumber, never, never>({
  resourcePath: "phone-numbers",
  includeCreate: false,
  includeUpdate: false,
  includeDelete: false,
});

// Type assertion to ensure get is non-optional since we enabled it
const basePhoneNumbersApiWithGet = basePhoneNumbersApi as {
  list: typeof basePhoneNumbersApi.list;
  get: NonNullable<typeof basePhoneNumbersApi.get>;
};

// Phone Numbers API
export const phoneNumbersApi = {
  ...basePhoneNumbersApiWithGet,

  getTelephonyStatus: async (workspaceId: string): Promise<PhoneNumberTelephonyStatus> => {
    return apiGet<PhoneNumberTelephonyStatus>(
      `/api/v1/workspaces/${workspaceId}/phone-numbers/telephony-status`,
    );
  },

  getInboundReadiness: async (workspaceId: string): Promise<PhoneNumbersInboundReadiness> => {
    return apiGet<PhoneNumbersInboundReadiness>(
      `/api/v1/workspaces/${workspaceId}/phone-numbers/inbound-readiness`,
    );
  },

  assignAgent: async (
    workspaceId: string,
    phoneNumberId: string,
    agentId: string,
  ): Promise<PhoneNumber> => {
    return apiPut<PhoneNumber>(`/api/v1/workspaces/${workspaceId}/phone-numbers/${phoneNumberId}`, {
      assigned_agent_id: agentId,
    });
  },

  search: async (
    workspaceId: string,
    params: SearchPhoneNumbersRequest,
  ): Promise<PhoneNumberSearchResult[]> => {
    return apiPost<PhoneNumberSearchResult[]>(
      `/api/v1/workspaces/${workspaceId}/phone-numbers/search`,
      params,
    );
  },

  purchase: async (
    workspaceId: string,
    data: PurchasePhoneNumberRequest,
  ): Promise<PhoneNumberPurchaseResult> => {
    return apiPost<PhoneNumberPurchaseResult>(
      `/api/v1/workspaces/${workspaceId}/phone-numbers/purchase`,
      data,
    );
  },

  release: async (workspaceId: string, phoneNumberId: string): Promise<{ success: boolean }> => {
    return apiDelete<{ success: boolean }>(
      `/api/v1/workspaces/${workspaceId}/phone-numbers/${phoneNumberId}`,
    );
  },

  sync: async (workspaceId: string): Promise<{ synced: number }> => {
    return apiPost<{ synced: number }>(`/api/v1/workspaces/${workspaceId}/phone-numbers/sync`, {});
  },
};
