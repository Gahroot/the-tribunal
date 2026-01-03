import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  conversationsApi,
  type ConversationsListParams,
} from "@/lib/api/conversations";

/**
 * Fetch and manage a list of conversations for a workspace
 */
export function useConversations(workspaceId: string, params: ConversationsListParams = {}) {
  return useQuery({
    queryKey: ["conversations", workspaceId, params],
    queryFn: () => conversationsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single conversation by ID with messages
 */
export function useConversation(workspaceId: string, conversationId: string) {
  return useQuery({
    queryKey: ["conversation", workspaceId, conversationId],
    queryFn: () => conversationsApi.get(workspaceId, conversationId),
    enabled: !!workspaceId && !!conversationId,
  });
}

/**
 * Send a message in a conversation
 */
export function useSendMessage(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { conversationId: string; body: string }) =>
      conversationsApi.sendMessage(workspaceId, data.conversationId, data.body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
}

/**
 * Toggle AI for a conversation
 */
export function useToggleConversationAI(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { conversationId: string; enabled: boolean }) =>
      conversationsApi.toggleAI(workspaceId, data.conversationId, data.enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
}

/**
 * Assign an agent to a conversation
 */
export function useAssignAgent(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { conversationId: string; agentId: string | null }) =>
      conversationsApi.assignAgent(workspaceId, data.conversationId, data.agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });
}
