import api from "@/lib/api";
import type { Tag } from "@/types";

export interface TagListResponse {
  items: Tag[];
  total: number;
}

export interface CreateTagRequest {
  name: string;
  color?: string;
}

export interface UpdateTagRequest {
  name?: string;
  color?: string;
}

export interface BulkTagRequest {
  contact_ids: number[];
  add_tag_ids?: string[];
  remove_tag_ids?: string[];
}

export interface BulkTagResponse {
  updated: number;
  errors: string[];
}

export const tagsApi = {
  list: async (workspaceId: string): Promise<TagListResponse> => {
    const response = await api.get<TagListResponse>(
      `/api/v1/workspaces/${workspaceId}/tags`
    );
    return response.data;
  },

  create: async (workspaceId: string, data: CreateTagRequest): Promise<Tag> => {
    const response = await api.post<Tag>(
      `/api/v1/workspaces/${workspaceId}/tags`,
      data
    );
    return response.data;
  },

  get: async (workspaceId: string, tagId: string): Promise<Tag> => {
    const response = await api.get<Tag>(
      `/api/v1/workspaces/${workspaceId}/tags/${tagId}`
    );
    return response.data;
  },

  update: async (workspaceId: string, tagId: string, data: UpdateTagRequest): Promise<Tag> => {
    const response = await api.put<Tag>(
      `/api/v1/workspaces/${workspaceId}/tags/${tagId}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, tagId: string): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/tags/${tagId}`);
  },

  bulkTag: async (workspaceId: string, data: BulkTagRequest): Promise<BulkTagResponse> => {
    const response = await api.post<BulkTagResponse>(
      `/api/v1/workspaces/${workspaceId}/tags/bulk-tag`,
      data
    );
    return response.data;
  },
};
