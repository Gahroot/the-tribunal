import api from "@/lib/api";
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
    const response = await api.get<SegmentContactsResponse>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}/contacts`
    );
    return response.data;
  },

  refresh: async (workspaceId: string, segmentId: string): Promise<Segment> => {
    const response = await api.post<Segment>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}/refresh`
    );
    return response.data;
  },
};
