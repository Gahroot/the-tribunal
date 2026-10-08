"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useContactConversations } from "@/hooks/useContactConversations";
import {
  useContactTimeline,
  useToggleContactAI,
  useDeleteContact,
} from "@/hooks/useContacts";
import { appointmentsApi } from "@/lib/api/appointments";
import { callsApi, type InitiateCallRequest } from "@/lib/api/calls";
import { phoneNumbersApi } from "@/lib/api/phone-numbers";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { Contact } from "@/types";

interface UseContactSidebarDataArgs {
  workspaceId: string | null | undefined;
  contact: Contact | null;
}

/**
 * Aggregates all data + mutations the contact sidebar needs.
 * Keeps the orchestrating component thin and focused on layout.
 */
export function useContactSidebarData({
  workspaceId,
  contact,
}: UseContactSidebarDataArgs) {
  const { data: timelineData } = useContactTimeline(
    workspaceId ?? "",
    contact?.id ?? 0,
  );
  const timeline = timelineData ?? [];

  const { data: appointmentsData, isPending: appointmentsLoading } = useQuery({
    queryKey: queryKeys.appointments.byContact(workspaceId ?? "", contact?.id),
    queryFn: () =>
      appointmentsApi.list(workspaceId!, {
        page: 1,
        page_size: 50,
        contact_id: contact!.id,
      }),
    enabled: !!workspaceId && !!contact,
  });

  const { data: phoneNumbersData } = useQuery({
    queryKey: queryKeys.phoneNumbers.all(workspaceId ?? ""),
    queryFn: () =>
      workspaceId
        ? phoneNumbersApi.list(workspaceId, { active_only: true })
        : Promise.resolve({
            items: [],
            total: 0,
            page: 1,
            page_size: 50,
            pages: 0,
          }),
    enabled: !!workspaceId,
  });

  const {
    data: conversationsData,
    isPending: aiLoading,
    isError: aiError,
    dataUpdatedAt,
  } = useContactConversations(workspaceId, contact?.id);

  const contactConversation = conversationsData?.items?.find(
    (conv) => conv.contact_id === contact?.id,
  );

  // Derive AI state from server, with optimistic override during toggle.
  // Storing the last-seen server value lets us reset the override when the
  // server value changes — without an effect (per react-hooks/set-state-in-effect).
  const serverAiEnabled = contactConversation?.ai_enabled ?? false;
  const scope = `${workspaceId}:${contact?.id}`;
  const [aiState, setAiState] = useState({
    scope,
    optimistic: null as boolean | null,
    lastServer: serverAiEnabled,
    dataUpdatedAt,
  });

  if (aiState.scope !== scope || aiState.lastServer !== serverAiEnabled || aiState.dataUpdatedAt !== dataUpdatedAt) {
    setAiState({ scope, optimistic: null, lastServer: serverAiEnabled, dataUpdatedAt });
  }

  const aiEnabled = aiState.scope === scope ? aiState.optimistic ?? serverAiEnabled : serverAiEnabled;
  // A late mutation callback for the previous contact must not change this one.
  const setAiEnabled = (value: boolean) =>
    setAiState((prev) => prev.scope === scope ? { ...prev, optimistic: value } : prev);

  const initiateCallMutation = useMutation({
    mutationFn: (data: InitiateCallRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return callsApi.initiate(workspaceId, data);
    },
    onSuccess: () => {
      toast.success("Call initiated successfully!");
    },
    onError: (error) => {
      toast.error(
        getApiErrorMessage(error, "Failed to initiate call. Please try again."),
      );
    },
  });

  const toggleAIMutation = useToggleContactAI(workspaceId ?? "");
  const deleteContactMutation = useDeleteContact(workspaceId ?? "");

  return {
    timeline,
    appointments: appointmentsData?.items ?? [],
    appointmentsLoading,
    phoneNumbers: phoneNumbersData?.items ?? [],
    aiEnabled,
    aiLoading,
    aiError,
    setAiEnabled,
    initiateCallMutation,
    toggleAIMutation,
    deleteContactMutation,
  };
}
