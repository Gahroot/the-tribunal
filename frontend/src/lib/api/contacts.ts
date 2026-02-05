import api from "@/lib/api";
import type { Contact, ContactStatus, TimelineItem } from "@/types";

export type ContactSortBy = "created_at" | "last_conversation" | "unread_first";

export interface ContactsListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: ContactStatus;
  sort_by?: ContactSortBy;
  // Advanced filters
  tags?: string;
  tags_match?: "any" | "all" | "none";
  lead_score_min?: number;
  lead_score_max?: number;
  is_qualified?: boolean;
  source?: string;
  company_name?: string;
  created_after?: string;
  created_before?: string;
  enrichment_status?: string;
  filters?: string; // JSON FilterDefinition
}

export interface ContactsListResponse {
  items: Contact[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateContactRequest {
  first_name: string;
  last_name?: string;
  email?: string;
  phone_number: string;
  company_name?: string;
  status?: ContactStatus;
  tags?: string[];
  notes?: string;
  source?: string;
}

export interface UpdateContactRequest {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone_number?: string;
  company_name?: string;
  status?: ContactStatus;
  tags?: string[];
  notes?: string;
}

export interface ImportErrorDetail {
  row: number;
  field: string | null;
  error: string;
}

export interface ImportResult {
  total_rows: number;
  successful: number;
  failed: number;
  skipped_duplicates: number;
  errors: ImportErrorDetail[];
  created_contacts: Contact[];
}

export interface ImportOptions {
  skip_duplicates?: boolean;
  default_status?: string;
  source?: string;
}

export interface BulkDeleteResponse {
  deleted: number;
  failed: number;
  errors: string[];
}

export interface ContactIdsResponse {
  ids: number[];
  total: number;
}

export interface ContactIdsParams {
  search?: string;
  status?: ContactStatus;
  // Advanced filters
  tags?: string;
  tags_match?: "any" | "all" | "none";
  lead_score_min?: number;
  lead_score_max?: number;
  is_qualified?: boolean;
  source?: string;
  company_name?: string;
  created_after?: string;
  created_before?: string;
  enrichment_status?: string;
  filters?: string;
}

export const contactsApi = {
  list: async (workspaceId: string, params: ContactsListParams = {}): Promise<ContactsListResponse> => {
    const response = await api.get<ContactsListResponse>(
      `/api/v1/workspaces/${workspaceId}/contacts`,
      { params }
    );
    return response.data;
  },

  listIds: async (workspaceId: string, params: ContactIdsParams = {}): Promise<ContactIdsResponse> => {
    const response = await api.get<ContactIdsResponse>(
      `/api/v1/workspaces/${workspaceId}/contacts/ids`,
      { params }
    );
    return response.data;
  },

  get: async (workspaceId: string, id: number): Promise<Contact> => {
    const response = await api.get<Contact>(
      `/api/v1/workspaces/${workspaceId}/contacts/${id}`
    );
    return response.data;
  },

  create: async (workspaceId: string, data: CreateContactRequest): Promise<Contact> => {
    const response = await api.post<Contact>(
      `/api/v1/workspaces/${workspaceId}/contacts`,
      data
    );
    return response.data;
  },

  update: async (workspaceId: string, id: number, data: UpdateContactRequest): Promise<Contact> => {
    const response = await api.put<Contact>(
      `/api/v1/workspaces/${workspaceId}/contacts/${id}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, id: number): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/contacts/${id}`);
  },

  bulkDelete: async (workspaceId: string, ids: number[]): Promise<BulkDeleteResponse> => {
    const response = await api.post<BulkDeleteResponse>(
      `/api/v1/workspaces/${workspaceId}/contacts/bulk-delete`,
      { ids }
    );
    return response.data;
  },

  getTimeline: async (
    workspaceId: string,
    contactId: number,
    limit: number = 100
  ): Promise<TimelineItem[]> => {
    const response = await api.get<TimelineItem[]>(
      `/api/v1/workspaces/${workspaceId}/contacts/${contactId}/timeline`,
      { params: { limit } }
    );
    return response.data;
  },

  toggleAI: async (
    workspaceId: string,
    contactId: number,
    enabled: boolean
  ): Promise<{ ai_enabled: boolean; conversation_id: string }> => {
    const response = await api.post<{ ai_enabled: boolean; conversation_id: string }>(
      `/api/v1/workspaces/${workspaceId}/contacts/${contactId}/ai/toggle`,
      { enabled }
    );
    return response.data;
  },

  importCSV: async (
    workspaceId: string,
    file: File,
    options: ImportOptions = {}
  ): Promise<ImportResult> => {
    const formData = new FormData();
    formData.append("file", file);
    if (options.skip_duplicates !== undefined) {
      formData.append("skip_duplicates", String(options.skip_duplicates));
    }
    if (options.default_status) {
      formData.append("default_status", options.default_status);
    }
    if (options.source) {
      formData.append("source", options.source);
    }

    const response = await api.post<ImportResult>(
      `/api/v1/workspaces/${workspaceId}/contacts/import`,
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      }
    );
    return response.data;
  },
};
