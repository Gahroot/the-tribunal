import { useQuery } from "@tanstack/react-query";

import { conversationsApi } from "@/lib/api/conversations";
import { queryKeys } from "@/lib/query-keys";

/** Separate the filtered payload from legacy workspace-wide contact caches. */
export function useContactConversations(
  workspaceId: string | null | undefined,
  contactId: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.conversations.scopedContact(workspaceId ?? "", contactId),
    queryFn: () => conversationsApi.listForContact(workspaceId!, contactId!),
    enabled: !!workspaceId && !!contactId,
  });
}
