// Container logic for the Nudges page: stats + list queries, act/dismiss/snooze
// mutations, pagination, and toast feedback. Presentational components stay dumb.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { nudgesApi } from "@/lib/api/nudges";
import { queryKeys } from "@/lib/query-keys";
import { formatDayMonth } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { NudgeListFilter } from "@/types/nudge";

import { DEFAULT_NUDGE_FILTER, PAGE_SIZE } from "./nudge-presentation";

export function useNudgesController(contactId?: number) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  // Default to unresolved work (pending + sent) so delivered nudges that still
  // need a human stay in view.
  const [statusFilter, setStatusFilter] = useState<NudgeListFilter>(DEFAULT_NUDGE_FILTER);
  const [page, setPage] = useState(1);

  const { data: stats, isPending: statsLoading } = useQuery({
    queryKey: queryKeys.nudges.stats(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return nudgesApi.getStats(workspaceId);
    },
    enabled: !!workspaceId && contactId === undefined,
  });

  const {
    data: nudgeList,
    isPending: listLoading,
    isError: listError,
    refetch: refetchList,
  } = useQuery({
    queryKey: queryKeys.nudges.list(workspaceId ?? "", {
      status: statusFilter,
      contact_id: contactId,
      page,
      page_size: PAGE_SIZE,
    }),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return nudgesApi.list(workspaceId, {
        status: statusFilter,
        contact_id: contactId,
        page,
        page_size: PAGE_SIZE,
      });
    },
    enabled: !!workspaceId,
  });

  const invalidateNudges = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.nudges.root() });
    // The Today queue's "nudges due today" item counts the same open nudges.
    if (workspaceId) {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.dashboard.todayQueue(workspaceId),
      });
    }
  };

  const actMutation = useMutation({
    mutationFn: ({ nudgeId, actionTaken }: { nudgeId: string; actionTaken?: string }) => {
      if (!workspaceId) throw new Error("No workspace");
      return nudgesApi.act(workspaceId, nudgeId, actionTaken);
    },
    onSuccess: (_data, variables) => {
      toast.success(variables.actionTaken === "send_card" ? "Card sent!" : "Marked as done");
      invalidateNudges();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed")),
  });

  const dismissMutation = useMutation({
    mutationFn: (nudgeId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return nudgesApi.dismiss(workspaceId, nudgeId);
    },
    onSuccess: () => {
      toast.success("Dismissed");
      invalidateNudges();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to dismiss")),
  });

  const snoozeMutation = useMutation({
    mutationFn: ({ nudgeId, snoozeUntil }: { nudgeId: string; snoozeUntil: string }) => {
      if (!workspaceId) throw new Error("No workspace");
      return nudgesApi.snooze(workspaceId, nudgeId, snoozeUntil);
    },
    onSuccess: (_data, variables) => {
      toast.success(`Snoozed until ${formatDayMonth(variables.snoozeUntil)}`);
      invalidateNudges();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to snooze")),
  });

  const totalPages = nudgeList ? Math.ceil(nudgeList.total / PAGE_SIZE) : 0;

  // Completing/dismissing the last item on the last page shrinks the scope;
  // step back to the new last page instead of showing an empty page. Adjusted
  // during render (not in an effect) so the stale page never paints.
  const lastPage = Math.max(1, totalPages);
  if (nudgeList && page > lastPage) {
    setPage(lastPage);
  }

  const changeStatusFilter = (status: NudgeListFilter) => {
    setStatusFilter(status);
    setPage(1);
  };

  return {
    stats,
    statsLoading,
    nudgeList,
    listLoading,
    listError,
    refetchList,
    statusFilter,
    changeStatusFilter,
    page,
    setPage,
    totalPages,
    act: (nudgeId: string, actionTaken?: string) => actMutation.mutate({ nudgeId, actionTaken }),
    dismiss: (nudgeId: string) => dismissMutation.mutate(nudgeId),
    snooze: (nudgeId: string, date: Date) =>
      snoozeMutation.mutate({ nudgeId, snoozeUntil: date.toISOString() }),
    isActing: actMutation.isPending,
    isDismissing: dismissMutation.isPending,
  };
}
