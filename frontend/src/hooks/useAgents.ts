import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  agentsApi,
  type AgentsListParams,
  type CreateAgentRequest,
  type UpdateAgentRequest,
} from "@/lib/api/agents";

/**
 * Fetch and manage a list of agents for a workspace
 */
export function useAgents(workspaceId: string, params: AgentsListParams = {}) {
  return useQuery({
    queryKey: ["agents", workspaceId, params],
    queryFn: () => agentsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single agent by ID
 */
export function useAgent(workspaceId: string, agentId: string) {
  return useQuery({
    queryKey: ["agent", workspaceId, agentId],
    queryFn: () => agentsApi.get(workspaceId, agentId),
    enabled: !!workspaceId && !!agentId,
  });
}

/**
 * Create a new agent
 */
export function useCreateAgent(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateAgentRequest) => agentsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
    },
  });
}

/**
 * Update an agent
 */
export function useUpdateAgent(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { agentId: string; data: UpdateAgentRequest }) =>
      agentsApi.update(workspaceId, variables.agentId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["agent"] });
    },
  });
}

/**
 * Delete an agent
 */
export function useDeleteAgent(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (agentId: string) => agentsApi.delete(workspaceId, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
    },
  });
}
