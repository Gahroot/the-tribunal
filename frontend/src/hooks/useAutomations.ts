import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  automationsApi,
  type AutomationsListParams,
  type CreateAutomationRequest,
  type UpdateAutomationRequest,
} from "@/lib/api/automations";

/**
 * Fetch and manage a list of automations for a workspace
 */
export function useAutomations(workspaceId: string, params: AutomationsListParams = {}) {
  return useQuery({
    queryKey: ["automations", workspaceId, params],
    queryFn: () => automationsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single automation by ID
 */
export function useAutomation(workspaceId: string, automationId: string) {
  return useQuery({
    queryKey: ["automation", workspaceId, automationId],
    queryFn: () => automationsApi.get(workspaceId, automationId),
    enabled: !!workspaceId && !!automationId,
  });
}

/**
 * Create a new automation
 */
export function useCreateAutomation(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateAutomationRequest) =>
      automationsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations", workspaceId] });
    },
  });
}

/**
 * Update an automation
 */
export function useUpdateAutomation(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { automationId: string; data: UpdateAutomationRequest }) =>
      automationsApi.update(workspaceId, variables.automationId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["automation"] });
    },
  });
}

/**
 * Delete an automation
 */
export function useDeleteAutomation(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (automationId: string) =>
      automationsApi.delete(workspaceId, automationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations", workspaceId] });
    },
  });
}

/**
 * Toggle automation active status
 */
export function useToggleAutomation(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (automationId: string) =>
      automationsApi.toggle(workspaceId, automationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["automation"] });
    },
  });
}
