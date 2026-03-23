import { apiGet, apiPost } from "@/lib/api";
import type { Segment, FilterDefinition } from "@/types";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";

export interface SegmentListResponse {
  items: Segment[];
  total: number;
}

export interface CreateSegmentRequest {
  name: string;
  description?: string;
  definition: FilterDefinition;
  is_dynamic?: boolean;
}

export interface UpdateSegmentRequest {
  name?: string;
  description?: string;
  definition?: FilterDefinition;
  is_dynamic?: boolean;
}

export interface SegmentContactsResponse {
  ids: number[];
  total: number;
}

const baseApi = createApiClient<Segment, CreateSegmentRequest, UpdateSegmentRequest>({
  resourcePath: "segments",
}) as FullApiClient<Segment, CreateSegmentRequest, UpdateSegmentRequest>;

export const segmentsApi = {
  ...baseApi,

  getContacts: async (workspaceId: string, segmentId: string): Promise<SegmentContactsResponse> => {
    return apiGet<SegmentContactsResponse>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}/contacts`
    );
  },

  refresh: async (workspaceId: string, segmentId: string): Promise<Segment> => {
    return apiPost<Segment>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}/refresh`
    );
  },
};
