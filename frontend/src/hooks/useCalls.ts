import { useQuery } from "@tanstack/react-query";
import { callsApi, type CallsListParams } from "@/lib/api/calls";

/**
 * Fetch and manage a list of calls for a workspace
 */
export function useCalls(workspaceId: string, params: CallsListParams = {}) {
  return useQuery({
    queryKey: ["calls", workspaceId, params],
    queryFn: () => callsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single call by ID
 */
export function useCall(workspaceId: string, callId: string) {
  return useQuery({
    queryKey: ["call", workspaceId, callId],
    queryFn: () => callsApi.get(workspaceId, callId),
    enabled: !!workspaceId && !!callId,
  });
}
