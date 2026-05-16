import { apiPost } from "@/lib/api";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";
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

const baseApi = createApiClient<Tag, CreateTagRequest, UpdateTagRequest>({
  resourcePath: "tags",
}) as FullApiClient<Tag, CreateTagRequest, UpdateTagRequest>;

export const tagsApi = {
  ...baseApi,

  bulkTag: async (workspaceId: string, data: BulkTagRequest): Promise<BulkTagResponse> => {
    return apiPost<BulkTagResponse>(
      `/api/v1/workspaces/${workspaceId}/tags/bulk-tag`,
      data
    );
  },
};
