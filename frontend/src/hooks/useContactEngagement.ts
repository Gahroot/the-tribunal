import { useQuery } from "@tanstack/react-query";

import { contactsApi, type ContactEngagementSummary } from "@/lib/api/contacts";
import { queryKeys } from "@/lib/query-keys";
import { POLL_30S } from "@/lib/query-options";

/**
 * Fetch aggregated engagement stats for a single contact.
 *
 * Updates with activity, so refetches on a short interval via POLL_30S.
 */
export function useContactEngagement(
  workspaceId: string,
  contactId: number | null,
) {
  return useQuery<ContactEngagementSummary>({
    queryKey: queryKeys.contacts.engagementSummary(
      workspaceId,
      String(contactId ?? ""),
    ),
    queryFn: () => contactsApi.getEngagementSummary(workspaceId, contactId!),
    enabled: !!workspaceId && !!contactId,
    ...POLL_30S,
  });
}
