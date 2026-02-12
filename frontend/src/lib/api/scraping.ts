import api from "@/lib/api";

export interface BusinessResult {
  place_id: string;
  name: string;
  address: string;
  phone_number: string | null;
  website: string | null;
  rating: number | null;
  review_count: number;
  types: string[];
  business_status: string;
  has_phone: boolean;
  has_website: boolean;
}

export interface BusinessSearchResponse {
  results: BusinessResult[];
  total_found: number;
  query: string;
}

export interface ImportLeadsRequest {
  leads: BusinessResult[];
  default_status?: string;
  add_tags?: string[];
}

export interface ImportLeadsResponse {
  total: number;
  imported: number;
  skipped_duplicates: number;
  skipped_no_phone: number;
  errors: string[];
}

export const scrapingApi = {
  search: async (
    workspaceId: string,
    query: string,
    maxResults: number = 20
  ): Promise<BusinessSearchResponse> => {
    const response = await api.post<BusinessSearchResponse>(
      `/api/v1/workspaces/${workspaceId}/scraping/search`,
      { query, max_results: maxResults }
    );
    return response.data;
  },

  importLeads: async (
    workspaceId: string,
    request: ImportLeadsRequest
  ): Promise<ImportLeadsResponse> => {
    const response = await api.post<ImportLeadsResponse>(
      `/api/v1/workspaces/${workspaceId}/scraping/import`,
      request
    );
    return response.data;
  },
};
