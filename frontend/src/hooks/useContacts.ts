import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  contactsApi,
  type ContactsListParams,
  type CreateContactRequest,
  type UpdateContactRequest,
  type ContactsListResponse,
} from "@/lib/api/contacts";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import type { Contact } from "@/types";
import type { ApiClient } from "@/lib/api/create-api-client";

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
 * Fetch ALL contacts across all pages for a workspace
 */
export function useAllContacts(workspaceId: string, params: Omit<ContactsListParams, 'page' | 'page_size'> = {}) {
  return useQuery({
    queryKey: ["all-contacts", workspaceId, params],
    queryFn: async (): Promise<ContactsListResponse> => {
      const allItems: Contact[] = [];
      let currentPage = 1;
      let totalPages = 1;
      const pageSize = 100; // Max allowed by backend

      // Fetch all pages
      while (currentPage <= totalPages) {
        const response = await contactsApi.list(workspaceId, {
          ...params,
          page: currentPage,
          page_size: pageSize,
        });

        allItems.push(...response.items);
        totalPages = response.pages;
        currentPage++;
      }

      return {
        items: allItems,
        total: allItems.length,
        page: 1,
        page_size: allItems.length,
        pages: 1,
      };
    },
    enabled: !!workspaceId,
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
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["all-contacts", workspaceId] });
    },
  });
}

/**
 * Fetch the timeline for a contact with live polling
 */
export function useContactTimeline(workspaceId: string, contactId: number, limit: number = 100) {
  return useQuery({
    queryKey: ["contact-timeline", workspaceId, contactId, limit],
    queryFn: () => contactsApi.getTimeline(workspaceId, contactId, limit),
    enabled: !!workspaceId && !!contactId,
    // Poll every 3 seconds for real-time updates
    refetchInterval: 3000,
    // Don't poll when the tab is not active
    refetchIntervalInBackground: false,
  });
}

/**
 * Toggle AI for a contact's conversation
 */
export function useToggleContactAI(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { contactId: number; enabled: boolean }) =>
      contactsApi.toggleAI(workspaceId, variables.contactId, variables.enabled),
    onSuccess: (_, variables) => {
      // Invalidate conversations to refresh AI state
      queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["contact-ai-state", workspaceId, variables.contactId] });
    },
  });
}
