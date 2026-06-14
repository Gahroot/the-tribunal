import { useQuery } from "@tanstack/react-query";

import {
  campaignsApi,
  type CreateCampaignRequest,
  type UpdateCampaignRequest,
} from "@/lib/api/campaigns";
import type { ApiClient } from "@/lib/api/create-api-client";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { queryKeys } from "@/lib/query-keys";
import type { Campaign } from "@/types";

const {
  queryKeys: campaignQueryKeys,
  useList: useCampaigns,
  useGet: useCampaign,
  useCreate: useCreateCampaign,
  useUpdate: useUpdateCampaign,
} = createResourceHooks({
  resourceKey: "campaigns",
  apiClient: campaignsApi as unknown as ApiClient<
    Campaign,
    CreateCampaignRequest,
    UpdateCampaignRequest
  >,
  includeDelete: false,
});

export { campaignQueryKeys, useCampaigns, useCampaign, useCreateCampaign, useUpdateCampaign };

export function useCampaignAnalytics(
  workspaceId: string,
  campaignId: string,
  options: { enabled?: boolean; refetchInterval?: number | false } = {},
) {
  return useQuery({
    queryKey: queryKeys.campaigns.analytics(workspaceId, campaignId),
    queryFn: () => campaignsApi.getAnalytics(workspaceId, campaignId),
    enabled: (options.enabled ?? true) && !!workspaceId && !!campaignId,
    refetchInterval: options.refetchInterval,
  });
}
