// Container logic for the Automations page: data fetching, mutation wiring,
// dialog/form state, and toast feedback. Presentational components stay dumb.
import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import {
  useAutomations,
  useCreateAutomation,
  useDeleteAutomation,
  useToggleAutomation,
  useUpdateAutomation,
} from "@/hooks/useAutomations";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { automationsApi } from "@/lib/api/automations";
import { queryKeys } from "@/lib/query-keys";
import type { Automation } from "@/types";

import {
  EMPTY_AUTOMATION_FORM,
  type AutomationFormState,
  automationToForm,
  buildCreatePayload,
  buildDuplicatePayload,
  buildUpdatePayload,
  countActive,
  filterAutomations,
} from "./automation-logic";

export function useAutomationsController() {
  const workspaceId = useWorkspaceId();
  const [searchQuery, setSearchQuery] = useState("");
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingAutomation, setEditingAutomation] = useState<Automation | null>(
    null,
  );
  const [form, setForm] = useState<AutomationFormState>(EMPTY_AUTOMATION_FORM);

  const { data, isPending, error } = useAutomations(workspaceId ?? "");
  const { data: statsData } = useQuery({
    queryKey: queryKeys.automations.stats(workspaceId ?? ""),
    queryFn: () => automationsApi.getStats(workspaceId!),
    enabled: !!workspaceId,
  });
  const createMutation = useCreateAutomation(workspaceId ?? "");
  const updateMutation = useUpdateAutomation(workspaceId ?? "");
  const deleteMutation = useDeleteAutomation(workspaceId ?? "");
  const toggleMutation = useToggleAutomation(workspaceId ?? "");

  const automations = data?.items ?? [];
  const filteredAutomations = filterAutomations(automations, searchQuery);
  const activeCount = countActive(automations);

  const isEditing = editingAutomation !== null;
  const isDialogOpen = isCreateDialogOpen || isEditing;

  const updateForm = useCallback((patch: Partial<AutomationFormState>) => {
    setForm((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetDialog = useCallback(() => {
    setIsCreateDialogOpen(false);
    setEditingAutomation(null);
    setForm(EMPTY_AUTOMATION_FORM);
  }, []);

  const openCreateDialog = useCallback(() => {
    setEditingAutomation(null);
    setForm(EMPTY_AUTOMATION_FORM);
    setIsCreateDialogOpen(true);
  }, []);

  const openConfigureDialog = useCallback((automation: Automation) => {
    setForm(automationToForm(automation));
    setEditingAutomation(automation);
  }, []);

  const onDialogOpenChange = useCallback(
    (open: boolean) => {
      if (!open) resetDialog();
    },
    [resetDialog],
  );

  const submitForm = useCallback(async () => {
    if (!form.name.trim()) {
      toast.error("Please enter a name for the automation");
      return;
    }

    try {
      if (editingAutomation) {
        await updateMutation.mutateAsync({
          id: editingAutomation.id,
          data: buildUpdatePayload(form),
        });
        toast.success("Automation updated successfully");
      } else {
        await createMutation.mutateAsync(buildCreatePayload(form));
        toast.success("Automation created successfully");
      }
      resetDialog();
    } catch {
      toast.error(
        editingAutomation
          ? "Failed to update automation"
          : "Failed to create automation",
      );
    }
  }, [form, editingAutomation, updateMutation, createMutation, resetDialog]);

  const toggleAutomation = useCallback(
    async (automation: Automation) => {
      try {
        await toggleMutation.mutateAsync(automation.id);
        toast.success(
          automation.is_active ? "Automation paused" : "Automation activated",
        );
      } catch {
        toast.error("Failed to toggle automation");
      }
    },
    [toggleMutation],
  );

  const deleteAutomation = useCallback(
    async (automation: Automation) => {
      try {
        await deleteMutation.mutateAsync(automation.id);
        toast.success("Automation deleted");
      } catch {
        toast.error("Failed to delete automation");
      }
    },
    [deleteMutation],
  );

  const duplicateAutomation = useCallback(
    async (automation: Automation) => {
      try {
        await createMutation.mutateAsync(buildDuplicatePayload(automation));
        toast.success("Automation duplicated");
      } catch {
        toast.error("Failed to duplicate automation");
      }
    },
    [createMutation],
  );

  return {
    searchQuery,
    setSearchQuery,
    automations,
    filteredAutomations,
    activeCount,
    triggeredToday: statsData?.triggered_today ?? 0,
    isPending,
    error,
    // Dialog + form
    isDialogOpen,
    isEditing,
    form,
    updateForm,
    onDialogOpenChange,
    openCreateDialog,
    openConfigureDialog,
    submitForm,
    isSubmitting: createMutation.isPending || updateMutation.isPending,
    // Row actions
    toggleAutomation,
    deleteAutomation,
    duplicateAutomation,
    isToggling: toggleMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isDuplicating: createMutation.isPending,
  };
}
