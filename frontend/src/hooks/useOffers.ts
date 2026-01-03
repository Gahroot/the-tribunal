import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  offersApi,
  type OffersListParams,
  type CreateOfferRequest,
  type UpdateOfferRequest,
} from "@/lib/api/offers";

/**
 * Fetch and manage a list of offers for a workspace
 */
export function useOffers(workspaceId: string, params: OffersListParams = {}) {
  return useQuery({
    queryKey: ["offers", workspaceId, params],
    queryFn: () => offersApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single offer by ID
 */
export function useOffer(workspaceId: string, offerId: string) {
  return useQuery({
    queryKey: ["offer", workspaceId, offerId],
    queryFn: () => offersApi.get(workspaceId, offerId),
    enabled: !!workspaceId && !!offerId,
  });
}

/**
 * Create a new offer
 */
export function useCreateOffer(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateOfferRequest) => offersApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
    },
  });
}

/**
 * Update an offer
 */
export function useUpdateOffer(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { offerId: string; data: UpdateOfferRequest }) =>
      offersApi.update(workspaceId, variables.offerId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["offer"] });
    },
  });
}

/**
 * Delete an offer
 */
export function useDeleteOffer(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (offerId: string) => offersApi.delete(workspaceId, offerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
    },
  });
}
