import { createApiClient } from "./create-api-client";
import api from "@/lib/api";
import type { Opportunity, Pipeline, PipelineStage } from "@/types";

export interface OpportunitiesListParams {
  page?: number;
  page_size?: number;
  search?: string;
  pipeline_id?: string;
  stage_id?: string;
}

export interface OpportunitiesListResponse {
  items: Opportunity[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateOpportunityRequest {
  name: string;
  description?: string;
  amount?: number;
  currency?: string;
  expected_close_date?: string;
  source?: string;
  pipeline_id: string;
  stage_id?: string;
  primary_contact_id?: number;
}

export interface UpdateOpportunityRequest {
  name?: string;
  description?: string;
  amount?: number;
  currency?: string;
  stage_id?: string;
  expected_close_date?: string;
  assigned_user_id?: string;
  source?: string;
  status?: "open" | "won" | "lost" | "abandoned";
  lost_reason?: string;
  is_active?: boolean;
}

export interface CreatePipelineRequest {
  name: string;
  description?: string;
}

export interface UpdatePipelineRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface CreatePipelineStageRequest {
  name: string;
  description?: string;
  order: number;
  probability: number;
  stage_type?: string;
}

export interface UpdatePipelineStageRequest {
  name?: string;
  description?: string;
  order?: number;
  probability?: number;
  stage_type?: string;
}

// Base API client using the factory for opportunity CRUD operations
const baseOpportunitiesApi = createApiClient<
  Opportunity,
  CreateOpportunityRequest,
  UpdateOpportunityRequest
>({
  resourcePath: "opportunities",
});

export const opportunitiesApi = {
  // Pipeline endpoints (custom)
  listPipelines: async (workspaceId: string): Promise<Pipeline[]> => {
    const response = await api.get<Pipeline[]>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines`
    );
    return response.data;
  },

  getPipeline: async (workspaceId: string, pipelineId: string): Promise<Pipeline> => {
    const response = await api.get<Pipeline>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}`
    );
    return response.data;
  },

  createPipeline: async (
    workspaceId: string,
    data: CreatePipelineRequest
  ): Promise<Pipeline> => {
    const response = await api.post<Pipeline>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines`,
      data
    );
    return response.data;
  },

  updatePipeline: async (
    workspaceId: string,
    pipelineId: string,
    data: UpdatePipelineRequest
  ): Promise<Pipeline> => {
    const response = await api.put<Pipeline>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}`,
      data
    );
    return response.data;
  },

  deletePipeline: async (workspaceId: string, pipelineId: string): Promise<void> => {
    await api.delete(`/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}`);
  },

  // Pipeline stage endpoints (custom)
  createStage: async (
    workspaceId: string,
    pipelineId: string,
    data: CreatePipelineStageRequest
  ): Promise<PipelineStage> => {
    const response = await api.post<PipelineStage>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}/stages`,
      data
    );
    return response.data;
  },

  updateStage: async (
    workspaceId: string,
    pipelineId: string,
    stageId: string,
    data: UpdatePipelineStageRequest
  ): Promise<PipelineStage> => {
    const response = await api.put<PipelineStage>(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}/stages/${stageId}`,
      data
    );
    return response.data;
  },

  // Opportunity CRUD from factory
  list: baseOpportunitiesApi.list,
  get: baseOpportunitiesApi.get!,
  create: baseOpportunitiesApi.create!,
  update: baseOpportunitiesApi.update!,
  delete: baseOpportunitiesApi.delete!,

  // Line item endpoints (custom)
  addLineItem: async (
    workspaceId: string,
    opportunityId: string,
    data: {
      name: string;
      description?: string;
      quantity: number;
      unit_price: number;
      discount?: number;
    }
  ): Promise<{ id: string; total: number }> => {
    const response = await api.post<{ id: string; total: number }>(
      `/api/v1/workspaces/${workspaceId}/opportunities/${opportunityId}/line-items`,
      data
    );
    return response.data;
  },

  updateLineItem: async (
    workspaceId: string,
    opportunityId: string,
    itemId: string,
    data: {
      name?: string;
      description?: string;
      quantity?: number;
      unit_price?: number;
      discount?: number;
    }
  ): Promise<{ id: string; total: number }> => {
    const response = await api.put<{ id: string; total: number }>(
      `/api/v1/workspaces/${workspaceId}/opportunities/${opportunityId}/line-items/${itemId}`,
      data
    );
    return response.data;
  },

  deleteLineItem: async (
    workspaceId: string,
    opportunityId: string,
    itemId: string
  ): Promise<void> => {
    await api.delete(
      `/api/v1/workspaces/${workspaceId}/opportunities/${opportunityId}/line-items/${itemId}`
    );
  },

  deleteStage: async (
    workspaceId: string,
    pipelineId: string,
    stageId: string
  ): Promise<void> => {
    await api.delete(
      `/api/v1/workspaces/${workspaceId}/opportunities/pipelines/${pipelineId}/stages/${stageId}`
    );
  },
};
