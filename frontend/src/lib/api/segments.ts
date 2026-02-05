import api from "@/lib/api";
import type { Segment, FilterDefinition } from "@/types";

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

export const segmentsApi = {
  list: async (workspaceId: string): Promise<SegmentListResponse> => {
    const response = await api.get<SegmentListResponse>(
      `/api/v1/workspaces/${workspaceId}/segments`
    );
    return response.data;
  },

  create: async (workspaceId: string, data: CreateSegmentRequest): Promise<Segment> => {
    const response = await api.post<Segment>(
      `/api/v1/workspaces/${workspaceId}/segments`,
      data
    );
    return response.data;
  },

  get: async (workspaceId: string, segmentId: string): Promise<Segment> => {
    const response = await api.get<Segment>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}`
    );
    return response.data;
  },

  update: async (workspaceId: string, segmentId: string, data: UpdateSegmentRequest): Promise<Segment> => {
    const response = await api.put<Segment>(
      `/api/v1/workspaces/${workspaceId}/segments/${segmentId}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, segmentId: string): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/segments/${segmentId}`);
  },

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
