// Container logic for the Automations page: data fetching, mutation wiring,
// dialog/form state, and toast feedback. Presentational components stay dumb.
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { useAgents } from "@/hooks/useAgents";
import {
  useAutomations,
  useCreateAutomation,
  useDeleteAutomation,
  useToggleAutomation,
  useUpdateAutomation,
} from "@/hooks/useAutomations";
import { useCampaigns } from "@/hooks/useCampaigns";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { automationsApi } from "@/lib/api/automations";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { Automation } from "@/types";

import type { AutomationOption } from "./automation-form-dialog";
import {
  EMPTY_AUTOMATION_FORM,
  type AutomationFormState,
  automationToForm,
  buildCreatePayload,
  buildDuplicatePayload,
  buildUpdatePayload,
  countActive,
  filterAutomations,
  getFormIssues,
} from "./automation-logic";

export function useAutomationsController() {
  const workspaceId = useWorkspaceId();
  const [searchQuery, setSearchQuery] = useState("");
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingAutomation, setEditingAutomation] = useState<Automation | null>(
    null,
  );
  const [form, setForm] = useState<AutomationFormState>(EMPTY_AUTOMATION_FORM);
  // Inline issues appear after the first save attempt (or when editing an
  // automation that already needs setup), not while the operator is typing.
  const [showIssues, setShowIssues] = useState(false);

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

  const isEditing = editingAutomation !== null;
  const isDialogOpen = isCreateDialogOpen || isEditing;
  // Option lists are only needed (and fetched) while the builder is open.
  const { data: campaignsData } = useCampaigns(
    isDialogOpen ? (workspaceId ?? "") : "",
    { page_size: 100 },
  );
  const { data: agentsData } = useAgents(
    isDialogOpen ? (workspaceId ?? "") : "",
    { active_only: true, page_size: 100 },
  );
  const campaignOptions = useMemo<AutomationOption[]>(
    () =>
      (campaignsData?.items ?? []).map((campaign) => ({
        id: campaign.id,
        name: campaign.name,
        hint: campaign.status,
      })),
    [campaignsData],
  );
  const agentOptions = useMemo<AutomationOption[]>(
    () =>
      (agentsData?.items ?? []).map((agent) => ({ id: agent.id, name: agent.name })),
    [agentsData],
  );
  const formIssues = useMemo(() => getFormIssues(form), [form]);

  const automations = data?.items ?? [];
  const filteredAutomations = filterAutomations(automations, searchQuery);
  const activeCount = countActive(automations);

  const updateForm = useCallback((patch: Partial<AutomationFormState>) => {
    setForm((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetDialog = useCallback(() => {
    setIsCreateDialogOpen(false);
    setEditingAutomation(null);
    setForm(EMPTY_AUTOMATION_FORM);
    setShowIssues(false);
  }, []);

  const openCreateDialog = useCallback(() => {
    setEditingAutomation(null);
    setForm(EMPTY_AUTOMATION_FORM);
    setShowIssues(false);
    setIsCreateDialogOpen(true);
  }, []);

  const openConfigureDialog = useCallback((automation: Automation) => {
    setForm(automationToForm(automation));
    setShowIssues(automation.readiness === "incomplete");
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
    if (form.isActive && formIssues.length > 0) {
      setShowIssues(true);
      toast.error("Finish setting up this automation, or turn off Active to save a draft.");
      return;
    }

    try {
      if (editingAutomation) {
        await updateMutation.mutateAsync({
          id: editingAutomation.id,
          data: buildUpdatePayload(form),
        });
        toast.success(
          form.isActive ? "Automation updated" : "Automation saved as draft",
        );
      } else {
        await createMutation.mutateAsync(buildCreatePayload(form));
        toast.success(
          form.isActive ? "Automation created and active" : "Automation saved as draft",
        );
      }
      resetDialog();
    } catch (err) {
      setShowIssues(true);
      toast.error(
        getApiErrorMessage(
          err,
          editingAutomation
            ? "Failed to update automation"
            : "Failed to create automation",
        ),
      );
    }
  }, [form, formIssues, editingAutomation, updateMutation, createMutation, resetDialog]);

  const toggleAutomation = useCallback(
    async (automation: Automation) => {
      try {
        await toggleMutation.mutateAsync(automation.id);
        toast.success(
          automation.is_active ? "Automation paused" : "Automation activated",
        );
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to toggle automation"));
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
    formIssues: showIssues ? formIssues : [],
    campaignOptions,
    agentOptions,
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
