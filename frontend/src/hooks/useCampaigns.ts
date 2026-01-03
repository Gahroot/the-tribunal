import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  campaignsApi,
  type CampaignsListParams,
  type CreateCampaignRequest,
  type UpdateCampaignRequest,
} from "@/lib/api/campaigns";

/**
 * Fetch and manage a list of campaigns for a workspace
 */
export function useCampaigns(workspaceId: string, params: CampaignsListParams = {}) {
  return useQuery({
    queryKey: ["campaigns", workspaceId, params],
    queryFn: () => campaignsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single campaign by ID
 */
export function useCampaign(workspaceId: string, campaignId: string) {
  return useQuery({
    queryKey: ["campaign", workspaceId, campaignId],
    queryFn: () => campaignsApi.get(workspaceId, campaignId),
    enabled: !!workspaceId && !!campaignId,
  });
}

/**
 * Create a new campaign
 */
export function useCreateCampaign(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateCampaignRequest) => campaignsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] });
    },
  });
}

/**
 * Update a campaign
 */
export function useUpdateCampaign(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { campaignId: string; data: UpdateCampaignRequest }) =>
      campaignsApi.update(workspaceId, variables.campaignId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["campaign"] });
    },
  });
}

/**
 * Fetch campaign analytics/stats
 */
export function useCampaignAnalytics(workspaceId: string, campaignId: string) {
  return useQuery({
    queryKey: ["campaignAnalytics", workspaceId, campaignId],
    queryFn: () => campaignsApi.getStats(workspaceId, campaignId),
    enabled: !!workspaceId && !!campaignId,
  });
}
