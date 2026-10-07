import api, { apiGet, apiPost } from "@/lib/api";

// ---- Request / Response Types ----

export interface RealtorOnboardRequest {
  calcom_api_key: string;
  calcom_event_type_id: number;
  area_code?: string;
  /** Stored on the target workspace so later FUB syncs use its credentials. */
  fub_api_key?: string;
}

export interface RealtorOnboardResponse {
  workspace_id: string;
  agent_id: string;
  phone_number_id: string | null;
  phone_number: string | null;
  /** False when no SMS number was auto-provisioned — campaigns can't launch yet. */
  phone_provisioned: boolean;
  calcom_connected: boolean;
  message: string;
}

export interface RealtorCampaignResponse {
  campaign_id: string;
  campaign_name: string;
  campaign_status: string;
  contacts_imported: number;
  contacts_skipped: number;
  contacts_failed: number;
  phone_number_used: string;
  agent_id: string;
  started_at: string | null;
  /** Workspace the campaign was launched in (echoes the explicit target). */
  workspace_id: string;
}

export interface VerifyCalcomResponse {
  valid: boolean;
  username?: string;
}

export interface ParseCalcomUrlResponse {
  event_type_id: number;
  slug: string;
}

export interface RealtorStats {
  leads_uploaded: number;
  texts_sent: number;
  replies_received: number;
  appointments_booked: number;
}

export interface VerifyFubResponse {
  valid: boolean;
  name?: string;
}

export interface FubContact {
  id: number;
  name: string;
  email?: string;
  phone?: string;
}

export interface FubContactsResponse {
  contacts: FubContact[];
  total: number;
}

export interface ImportFubContactsResponse {
  imported: number;
  message: string;
}

// ---- API Functions ----

export function verifyFub(apiKey: string): Promise<VerifyFubResponse> {
  return apiPost<VerifyFubResponse>("/api/v1/realtor/verify-fub", { api_key: apiKey });
}

export function getFubContacts(
  workspaceId: string,
  limit = 100,
  offset = 0
): Promise<FubContactsResponse> {
  return apiGet<FubContactsResponse>(
    `/api/v1/workspaces/${workspaceId}/realtor/fub-contacts`,
    { params: { limit, offset } }
  );
}

export function importFubContacts(
  workspaceId: string,
  importAll: boolean,
  contactIds?: number[],
  /** When set, stored on this workspace before importing (guided setup). */
  apiKey?: string
): Promise<ImportFubContactsResponse> {
  return apiPost<ImportFubContactsResponse>(
    `/api/v1/workspaces/${workspaceId}/realtor/import-fub-contacts`,
    {
      import_all: importAll,
      contact_ids: contactIds,
      api_key: apiKey || undefined,
    }
  );
}

export function getRealtorStats(workspaceId: string): Promise<RealtorStats> {
  return apiGet<RealtorStats>(`/api/v1/workspaces/${workspaceId}/realtor/stats`);
}

export function verifyCalcom(apiKey: string): Promise<VerifyCalcomResponse> {
  return apiGet<VerifyCalcomResponse>("/api/v1/realtor/verify-calcom", {
    params: { api_key: apiKey },
  });
}

export function parseCalcomUrl(
  workspaceId: string,
  url: string,
  apiKey?: string
): Promise<ParseCalcomUrlResponse> {
  return apiPost<ParseCalcomUrlResponse>(
    `/api/v1/workspaces/${workspaceId}/realtor/parse-calcom-url`,
    { url, api_key: apiKey }
  );
}

/** Idempotent: retries reuse the workspace's realtor agent and SMS number. */
export function onboard(
  workspaceId: string,
  data: RealtorOnboardRequest
): Promise<RealtorOnboardResponse> {
  return apiPost<RealtorOnboardResponse>(
    `/api/v1/workspaces/${workspaceId}/realtor/onboard`,
    data
  );
}

export function createCampaignFromCsv(
  workspaceId: string,
  file: File,
  options: {
    skipDuplicates?: boolean;
    campaignName?: string;
    areaCode?: string;
  } = {}
): Promise<RealtorCampaignResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.skipDuplicates !== undefined) {
    formData.append("skip_duplicates", String(options.skipDuplicates));
  }
  if (options.campaignName) {
    formData.append("campaign_name", options.campaignName);
  }
  if (options.areaCode) {
    formData.append("area_code", options.areaCode);
  }

  return api
    .post<RealtorCampaignResponse>(
      `/api/v1/workspaces/${workspaceId}/realtor/campaigns`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    )
    .then((r) => r.data);
}
