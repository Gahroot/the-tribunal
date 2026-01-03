import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  contactsApi,
  type ContactsListParams,
  type CreateContactRequest,
  type UpdateContactRequest,
} from "@/lib/api/contacts";

/**
 * Fetch and manage a list of contacts for a workspace
 */
export function useContacts(workspaceId: string, params: ContactsListParams = {}) {
  return useQuery({
    queryKey: ["contacts", workspaceId, params],
    queryFn: () => contactsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single contact by ID
 */
export function useContact(workspaceId: string, contactId: number) {
  return useQuery({
    queryKey: ["contact", workspaceId, contactId],
    queryFn: () => contactsApi.get(workspaceId, contactId),
    enabled: !!workspaceId && !!contactId,
  });
}

/**
 * Create a new contact
 */
export function useCreateContact(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateContactRequest) => contactsApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
    },
  });
}

/**
 * Update a contact
 */
export function useUpdateContact(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { contactId: number; data: UpdateContactRequest }) =>
      contactsApi.update(workspaceId, variables.contactId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["contact"] });
    },
  });
}

/**
 * Delete a contact
 */
export function useDeleteContact(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (contactId: number) => contactsApi.delete(workspaceId, contactId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
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
