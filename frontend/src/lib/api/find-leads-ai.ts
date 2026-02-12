import api from "@/lib/api";
import type { BusinessResult, BusinessSearchResponse } from "./scraping";

export interface LeadImportDetail {
  name: string;
  status: "imported" | "rejected_low_score" | "enrichment_failed" | "skipped_duplicate" | "skipped_no_phone";
  lead_score: number | null;
  revenue_tier: string | null;
  decision_maker_name: string | null;
  decision_maker_title: string | null;
}

export interface AIImportLeadsRequest {
  leads: BusinessResult[];
  default_status?: string;
  add_tags?: string[];
  enable_enrichment?: boolean;
  min_lead_score?: number;
}

export interface AIImportLeadsResponse {
  total: number;
  imported: number;
  rejected_low_score: number;
  enrichment_failed: number;
  skipped_duplicates: number;
  skipped_no_phone: number;
  queued_for_enrichment: number; // Always 0 (enrichment is now synchronous)
  errors: string[];
  lead_details: LeadImportDetail[];
}

export const findLeadsAIApi = {
  search: async (
    workspaceId: string,
    query: string,
    maxResults: number = 40
  ): Promise<BusinessSearchResponse> => {
    const response = await api.post<BusinessSearchResponse>(
      `/api/v1/workspaces/${workspaceId}/find-leads-ai/search`,
      { query, max_results: maxResults }
    );
    return response.data;
  },

  importLeads: async (
    workspaceId: string,
    request: AIImportLeadsRequest
  ): Promise<AIImportLeadsResponse> => {
    const response = await api.post<AIImportLeadsResponse>(
      `/api/v1/workspaces/${workspaceId}/find-leads-ai/import`,
      request
    );
    return response.data;
  },
};

// Re-export types for convenience
export type { BusinessResult, BusinessSearchResponse };
