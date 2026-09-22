import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import {
  contactsApi,
  type ContactsListParams,
  type ContactIdsParams,
  type CreateContactRequest,
  type UpdateContactRequest,
} from "@/lib/api/contacts";
import type { ApiClient } from "@/lib/api/create-api-client";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { queryKeys } from "@/lib/query-keys";
import { REALTIME } from "@/lib/query-options";
import type { Contact, ContactStatus, Conversation } from "@/types";

/** Paginated conversations payload cached under `conversations.byContact`. */
interface ContactConversationsCache {
  items: Conversation[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/**
 * Apply an optimistic patch to a contact's cached conversation so AI/agent
 * controls update instantly. This cache holds all of the workspace's threads
 * (the feed filters client-side), so we patch ONLY the thread linked by
 * `contact_id` — never a positional fallback, which could touch an unrelated
 * contact. When no linked thread is cached yet (phone-linked but not
 * backfilled, or not created), we skip the optimistic patch and let the
 * `onSettled` refetch reconcile. Returns the previous cache for rollback.
 */
function patchContactConversationCache(
  queryClient: ReturnType<typeof useQueryClient>,
  workspaceId: string,
  contactId: number,
  patch: Partial<Conversation>,
): ContactConversationsCache | undefined {
  const queryKey = queryKeys.conversations.byContact(workspaceId, contactId);
  const previous = queryClient.getQueryData<ContactConversationsCache>(queryKey);
  if (!previous) return undefined;

  const hasLinkedThread = previous.items.some(
    (conv) => conv.contact_id === contactId,
  );
  if (!hasLinkedThread) return previous;

  queryClient.setQueryData<ContactConversationsCache>(queryKey, {
    ...previous,
    items: previous.items.map((conv) =>
      conv.contact_id === contactId ? { ...conv, ...patch } : conv,
    ),
  });

  return previous;
}

const {
  queryKeys: contactQueryKeys,
  useList: useContacts,
  useGet: useContact,
  useCreate: useCreateContact,
  useUpdate: useUpdateContact,
  useDelete: useDeleteContact,
} = createResourceHooks({
  resourceKey: "contacts",
  apiClient: contactsApi as unknown as ApiClient<Contact, CreateContactRequest, UpdateContactRequest>,
});

export { contactQueryKeys, useContacts, useContact, useCreateContact, useUpdateContact, useDeleteContact };

/**
 * Fetch a single page of contacts with server-side filtering/sorting/pagination
 */
export function useContactsPaginated(workspaceId: string, params: ContactsListParams) {
  return useQuery({
    queryKey: queryKeys.contacts.list(workspaceId, params),
    queryFn: () => contactsApi.list(workspaceId, params),
    enabled: !!workspaceId,
    placeholderData: keepPreviousData,
  });
}

/**
 * Bulk delete contacts
 */
export function useBulkDeleteContacts(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ids: number[]) => contactsApi.bulkDelete(workspaceId, ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.all(workspaceId) });
    },
  });
}

/**
 * Fetch the timeline for a contact with live polling
 */
export function useContactTimeline(workspaceId: string, contactId: number, limit: number = 100) {
  return useQuery({
    queryKey: queryKeys.contacts.timeline(workspaceId, contactId, limit),
    queryFn: () => contactsApi.getTimeline(workspaceId, contactId, limit),
    enabled: !!workspaceId && !!contactId,
    ...REALTIME,
    // Don't poll when the tab is not active
    refetchIntervalInBackground: false,
  });
}

/**
 * Bulk update contact status
 */
export function useBulkUpdateStatus(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { ids: number[]; status: ContactStatus }) =>
      contactsApi.bulkUpdateStatus(workspaceId, variables.ids, variables.status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.all(workspaceId) });
    },
  });
}

/**
 * Fetch all contact IDs matching current filters (for select-all)
 */
export function useContactIds(
  workspaceId: string,
  params: ContactIdsParams,
  enabled: boolean,
  onSuccess?: (data: Awaited<ReturnType<typeof contactsApi.listIds>>) => void
) {
  return useQuery({
    queryKey: queryKeys.contacts.ids(workspaceId, { ...params }),
    queryFn: async () => {
      const data = await contactsApi.listIds(workspaceId, params);
      onSuccess?.(data);
      return data;
    },
    enabled: !!workspaceId && enabled,
  });
}

/**
 * Toggle AI for a contact's conversation.
 *
 * Uses the contact-level endpoint, which finds-or-creates the conversation
 * server-side — so it works even before the first message exists. Optimistic
 * cache patch + rollback keeps the chat header toggle instant and consistent.
 */
export function useToggleContactAI(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { contactId: number; enabled: boolean }) =>
      contactsApi.toggleAI(workspaceId, variables.contactId, variables.enabled),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.conversations.byContact(workspaceId, variables.contactId),
      });
      const previous = patchContactConversationCache(
        queryClient,
        workspaceId,
        variables.contactId,
        { ai_enabled: variables.enabled },
      );
      return { previous };
    },
    onError: (_err, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          queryKeys.conversations.byContact(workspaceId, variables.contactId),
          context.previous,
        );
      }
    },
    onSettled: (_data, _err, variables) => {
      // Reconcile with the server (also picks up a freshly-created conversation).
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all(workspaceId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.aiState(workspaceId, variables.contactId),
      });
    },
  });
}

/**
 * Assign an AI agent to a contact's active conversation.
 *
 * Mirrors the backend rule: assigning an agent enables AI, unassigning
 * disables it. Optimistic patch + rollback for instant, consistent UI.
 */
export function useAssignContactAgent(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { contactId: number; agentId: string | null }) =>
      contactsApi.assignAgent(workspaceId, variables.contactId, variables.agentId),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.conversations.byContact(workspaceId, variables.contactId),
      });
      const previous = patchContactConversationCache(
        queryClient,
        workspaceId,
        variables.contactId,
        {
          assigned_agent_id: variables.agentId ?? undefined,
          ai_enabled: variables.agentId !== null,
        },
      );
      return { previous };
    },
    onError: (_err, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          queryKeys.conversations.byContact(workspaceId, variables.contactId),
          context.previous,
        );
      }
    },
    onSettled: (_data, _err, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all(workspaceId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.aiState(workspaceId, variables.contactId),
      });
    },
  });
}
