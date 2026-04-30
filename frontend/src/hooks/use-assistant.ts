/** React Query hooks for CRM assistant chat. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { assistantApi } from "@/lib/api/assistant";
import { queryKeys } from "@/lib/query-keys";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export function useAssistantHistory() {
  const workspaceId = useWorkspaceId();

  return useQuery({
    queryKey: queryKeys.assistant.history(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return assistantApi.getHistory(workspaceId);
    },
    enabled: !!workspaceId,
    refetchOnWindowFocus: false,
  });
}

export function useAssistantChat() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  const historyKey = queryKeys.assistant.history(workspaceId ?? "");

  return useMutation({
    mutationFn: (message: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return assistantApi.chat(workspaceId, message);
    },

    // Optimistically append the user message + a loading placeholder
    onMutate: async (message) => {
      await queryClient.cancelQueries({ queryKey: historyKey });

      const previous = queryClient.getQueryData(historyKey);

      queryClient.setQueryData(historyKey, (old: unknown) => {
        const conv = old as {
          id: string;
          messages: { id: string; role: string; content: string; created_at: string }[];
        } | null;
        if (!conv) {
          return {
            id: "temp",
            messages: [
              {
                id: "temp-user",
                role: "user",
                content: message,
                created_at: new Date().toISOString(),
              },
              {
                id: "temp-loading",
                role: "assistant",
                content: "…",
                created_at: new Date().toISOString(),
              },
            ],
            created_at: new Date().toISOString(),
          };
        }
        return {
          ...conv,
          messages: [
            ...conv.messages,
            {
              id: "temp-user",
              role: "user",
              content: message,
              created_at: new Date().toISOString(),
            },
            {
              id: "temp-loading",
              role: "assistant",
              content: "…",
              created_at: new Date().toISOString(),
            },
          ],
        };
      });

      return { previous };
    },

    // On success, refetch real history from server
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: historyKey });
    },

    // On error, rollback optimistic update
    onError: (_err, _message, context) => {
      if (context?.previous) {
        queryClient.setQueryData(historyKey, context.previous);
      }
    },
  });
}
