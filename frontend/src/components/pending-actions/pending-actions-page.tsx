"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageEmptyState, PageErrorState, PageLoadingState } from "@/components/ui/page-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { pendingActionsApi } from "@/lib/api/pending-actions";
import { queryKeys } from "@/lib/query-keys";
import { POLL_60S } from "@/lib/query-options";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { PendingActionStatus } from "@/types/pending-action";

import { PendingActionCard } from "./pending-action-card";

type TabStatus = PendingActionStatus | "all";

// Pending leads: it is the default view and the tab this cockpit is built for.
const STATUS_TABS: { value: TabStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
  { value: "failed", label: "Failed" },
  { value: "all", label: "All" },
];

const PAGE_SIZE = 20;

const SNOOZE_STORAGE_PREFIX = "pending-actions.snooze";

type SnoozeMap = Record<string, number>;

interface SnoozeState {
  workspaceId: string | null;
  map: SnoozeMap;
}

function snoozeStorageKey(workspaceId: string): string {
  return `${SNOOZE_STORAGE_PREFIX}.${workspaceId}`;
}

/**
 * Snooze is a local review deferral: it hides an action from the pending list
 * until a chosen time (never past the auto-reject deadline) and remembers that
 * choice on this device. The backend has no snooze endpoint, so the action's
 * real lifecycle (auto-reject at `expires_at`) is unchanged.
 */
function readSnoozes(workspaceId: string): SnoozeMap {
  try {
    const raw = window.localStorage.getItem(snoozeStorageKey(workspaceId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const now = Date.now();
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        (entry): entry is [string, number] => typeof entry[1] === "number" && entry[1] > now,
      ),
    );
  } catch {
    return {}; // Storage can be unavailable (private mode, quota); snooze just won't persist.
  }
}

function writeSnoozes(workspaceId: string, snoozes: SnoozeMap): void {
  try {
    window.localStorage.setItem(snoozeStorageKey(workspaceId), JSON.stringify(snoozes));
  } catch {
    // Persisting is best-effort; the in-memory state still works for this visit.
  }
}

export function PendingActionsPage() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<TabStatus>("pending");
  const [page, setPage] = useState(1);
  const [rejectActionId, setRejectActionId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [batchOpen, setBatchOpen] = useState(false);
  const [showSnoozed, setShowSnoozed] = useState(false);
  // The map is tagged with the workspace it was loaded for, so a workspace
  // switch can neither display nor persist another tenant's snoozes.
  const [snoozeState, setSnoozeState] = useState<SnoozeState>({
    workspaceId: null,
    map: {},
  });

  const { data: stats } = useQuery({
    queryKey: queryKeys.pendingActions.stats(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return pendingActionsApi.getStats(workspaceId);
    },
    enabled: !!workspaceId,
    ...POLL_60S,
  });

  const {
    data: actionList,
    isPending: listLoading,
    isError: listError,
    refetch: refetchList,
  } = useQuery({
    queryKey: queryKeys.pendingActions.list(workspaceId ?? "", { status: statusFilter, page }),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return pendingActionsApi.list(workspaceId, {
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: PAGE_SIZE,
      });
    },
    enabled: !!workspaceId,
    ...POLL_60S,
  });

  // Load snoozes after mount so server and first client render match; until
  // the map is tagged for the active workspace, reads stay empty rather than
  // leaking another workspace's state.
  useEffect(() => {
    if (!workspaceId) return;
    setSnoozeState({ workspaceId, map: readSnoozes(workspaceId) });
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId || snoozeState.workspaceId !== workspaceId) return;
    writeSnoozes(workspaceId, snoozeState.map);
  }, [workspaceId, snoozeState]);

  // Reveal snoozed actions when their deferral ends (checked every 30s).
  useEffect(() => {
    const prune = () =>
      setSnoozeState((prev) => {
        const now = Date.now();
        const next = Object.fromEntries(
          Object.entries(prev.map).filter(([, until]) => until > now),
        );
        return Object.keys(next).length === Object.keys(prev.map).length
          ? prev
          : { ...prev, map: next };
      });
    const timer = setInterval(prune, 30_000);
    return () => clearInterval(timer);
  }, []);

  const invalidateActions = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.pendingActions.root() });
  };

  const approveMutation = useMutation({
    mutationFn: (actionId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return pendingActionsApi.approve(workspaceId, actionId);
    },
    onSuccess: () => {
      toast.success("Action approved");
      invalidateActions();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to approve action")),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ actionId, reason }: { actionId: string; reason?: string }) => {
      if (!workspaceId) throw new Error("No workspace");
      return pendingActionsApi.reject(workspaceId, actionId, reason);
    },
    onSuccess: () => {
      toast.success("Action rejected");
      invalidateActions();
      setRejectActionId(null);
      setRejectReason("");
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to reject action")),
  });

  const batchApproveMutation = useMutation({
    mutationFn: async (actionIds: string[]) => {
      if (!workspaceId) throw new Error("No workspace");
      return Promise.allSettled(
        actionIds.map((actionId) => pendingActionsApi.approve(workspaceId, actionId)),
      );
    },
    onSuccess: (results) => {
      const approved = results.filter((result) => result.status === "fulfilled").length;
      const failed = results.length - approved;
      if (failed === 0) {
        toast.success(`${approved} action${approved === 1 ? "" : "s"} approved`);
      } else if (approved === 0) {
        const firstError = results.find(
          (result): result is PromiseRejectedResult => result.status === "rejected",
        );
        toast.error(
          firstError
            ? getApiErrorMessage(firstError.reason, "Failed to approve these actions")
            : "Failed to approve these actions",
        );
      } else {
        toast.warning(
          `Approved ${approved} of ${results.length}. The rest may have changed since you selected them.`,
        );
      }
      setSelected(new Set());
      setBatchOpen(false);
      invalidateActions();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to approve actions")),
  });

  const handleTabChange = (value: string) => {
    setStatusFilter(value as TabStatus);
    setPage(1);
    setSelected(new Set());
    setShowSnoozed(false);
    setBatchOpen(false);
  };

  const handlePageChange = (nextPage: number) => {
    setPage(nextPage);
    setSelected(new Set());
    setBatchOpen(false);
  };

  const handleSnooze = (actionId: string, until: Date) => {
    setSnoozeState((prev) => ({
      workspaceId,
      map: {
        ...(prev.workspaceId === workspaceId ? prev.map : {}),
        [actionId]: until.getTime(),
      },
    }));
    toast.success(`Snoozed until ${formatTime(until)}`);
  };

  const handleUndoSnooze = (actionId: string) => {
    setSnoozeState((prev) => {
      if (prev.workspaceId !== workspaceId || !(actionId in prev.map)) return prev;
      const map = { ...prev.map };
      delete map[actionId];
      return { ...prev, map };
    });
  };

  const items = actionList?.items ?? [];
  const isPendingTab = statusFilter === "pending";
  const snoozes = snoozeState.workspaceId === workspaceId ? snoozeState.map : {};
  const snoozedCount = isPendingTab ? items.filter((action) => snoozes[action.id]).length : 0;
  const visibleItems =
    isPendingTab && !showSnoozed ? items.filter((action) => !snoozes[action.id]) : items;

  // Selection exists only on the pending tab, where every listed row can be
  // approved; selections are cleared whenever the list context changes.
  const selectableIds = isPendingTab ? visibleItems.map((action) => action.id) : [];
  const selectedIds = selectableIds.filter((id) => selected.has(id));
  const allSelected = selectableIds.length > 0 && selectedIds.length === selectableIds.length;
  const someSelected = selectedIds.length > 0 && !allSelected;
  const selectedItems = isPendingTab
    ? visibleItems.filter((action) => selected.has(action.id))
    : [];
  const batchPending = batchApproveMutation.isPending;

  const totalPages = actionList ? Math.ceil(actionList.total / PAGE_SIZE) : 0;
  const allVisibleSnoozed =
    isPendingTab && !showSnoozed && items.length > 0 && visibleItems.length === 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-6 p-6">
        {/* Header: one pending count, neutral surface with a single marker */}
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
            <p className="text-sm text-muted-foreground">
              Review what the AI wants to do. Unattended actions are auto-rejected (never sent) when
              they expire.
            </p>
          </div>
          {stats ? (
            <span className="inline-flex shrink-0 items-center gap-2 rounded-full border bg-muted px-3 py-1 text-sm font-medium">
              <span aria-hidden="true" className="size-2 rounded-full bg-warning" />
              {stats.pending} pending action{stats.pending === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>

        {/* Status tabs + selection toolbar. A single Tabs root keeps triggers
            and panels associated for assistive tech. */}
        <Tabs value={statusFilter} onValueChange={handleTabChange}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TabsList>
              {STATUS_TABS.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {isPendingTab ? (
              <div className="flex flex-wrap items-center justify-end gap-3">
                {visibleItems.length > 0 ? (
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={(checked) =>
                        setSelected(checked === true ? new Set(selectableIds) : new Set())
                      }
                      aria-label="Select all actions on this page"
                    />
                    <span className="text-sm text-muted-foreground">Select all</span>
                  </div>
                ) : null}

                <div aria-live="polite" className="flex items-center gap-2">
                  {selectedIds.length > 0 ? (
                    <>
                      <span className="text-sm font-medium">{selectedIds.length} selected</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelected(new Set());
                          setBatchOpen(false);
                        }}
                      >
                        Clear
                      </Button>
                      <Button size="sm" onClick={() => setBatchOpen(true)} disabled={batchPending}>
                        Approve selected ({selectedIds.length})
                      </Button>
                    </>
                  ) : null}
                </div>

                {snoozedCount > 0 ? (
                  <Button
                    variant="outline"
                    size="sm"
                    aria-pressed={showSnoozed}
                    className={cn(showSnoozed && "border-primary/50")}
                    onClick={() => setShowSnoozed((value) => !value)}
                  >
                    {showSnoozed ? "Hide snoozed" : `Snoozed ${snoozedCount}`}
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>

          {STATUS_TABS.map((tab) => (
            <TabsContent key={tab.value} value={tab.value} className="mt-4">
              {listLoading ? (
                <ActionListSkeleton />
              ) : listError ? (
                <Card>
                  <CardContent className="py-4">
                    <PageErrorState
                      message="We couldn't load pending actions. Please try again."
                      onRetry={() => refetchList()}
                    />
                  </CardContent>
                </Card>
              ) : visibleItems.length === 0 ? (
                allVisibleSnoozed ? (
                  <SnoozedEmptyState count={snoozedCount} onShow={() => setShowSnoozed(true)} />
                ) : (
                  <ActionEmptyState status={tab.value} />
                )
              ) : (
                <div className="space-y-3">
                  {visibleItems.map((action) => (
                    <PendingActionCard
                      key={action.id}
                      action={action}
                      onApprove={() => approveMutation.mutate(action.id)}
                      onReject={() => {
                        setRejectActionId(action.id);
                        setRejectReason("");
                      }}
                      isApproving={
                        (approveMutation.isPending && approveMutation.variables === action.id) ||
                        batchPending
                      }
                      isRejecting={
                        rejectMutation.isPending && rejectMutation.variables?.actionId === action.id
                      }
                      showStatus={tab.value === "all"}
                      selected={selected.has(action.id)}
                      onSelectedChange={
                        tab.value === "pending"
                          ? (isSelected) =>
                              setSelected((prev) => {
                                const next = new Set(prev);
                                if (isSelected) next.add(action.id);
                                else next.delete(action.id);
                                return next;
                              })
                          : undefined
                      }
                      snooze={
                        tab.value === "pending"
                          ? {
                              snoozedUntil: snoozes[action.id] ?? null,
                              onSnooze: (until) => handleSnooze(action.id, until),
                              onUndoSnooze: () => handleUndoSnooze(action.id),
                            }
                          : undefined
                      }
                    />
                  ))}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between pt-4">
                      <p className="text-sm text-muted-foreground">
                        Page {page} of {totalPages} ({actionList?.total ?? 0} action
                        {(actionList?.total ?? 0) !== 1 && "s"})
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page <= 1}
                          onClick={() => handlePageChange(page - 1)}
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page >= totalPages}
                          onClick={() => handlePageChange(page + 1)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* Batch approve confirmation */}
      <Dialog
        open={batchOpen && selectedIds.length > 0}
        onOpenChange={(open) => {
          if (!batchPending) setBatchOpen(open);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Approve {selectedIds.length} action{selectedIds.length === 1 ? "" : "s"}?
            </DialogTitle>
            <DialogDescription>
              The AI runs these as soon as they&apos;re approved. This can&apos;t be undone.
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-3 text-sm">
            {selectedItems.map((action) => (
              <li key={action.id} className="break-words">
                {action.description}
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setBatchOpen(false)} disabled={batchPending}>
              Cancel
            </Button>
            <Button
              onClick={() => batchApproveMutation.mutate(selectedIds)}
              disabled={batchPending}
            >
              {batchPending
                ? "Approving..."
                : `Approve ${selectedIds.length} action${selectedIds.length === 1 ? "" : "s"}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={!!rejectActionId} onOpenChange={() => setRejectActionId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Action</DialogTitle>
            <DialogDescription>
              Rejection is final: the AI won&apos;t run this action. Optionally record why.
            </DialogDescription>
          </DialogHeader>
          <label htmlFor="reject-reason" className="text-sm font-medium">
            Reason <span className="font-normal text-muted-foreground">(optional)</span>
          </label>
          <Textarea
            id="reject-reason"
            placeholder="Reason for rejection"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectActionId(null)}>
              Cancel
            </Button>
            <Button
              variant="outline"
              className="font-semibold"
              onClick={() =>
                rejectActionId &&
                rejectMutation.mutate({
                  actionId: rejectActionId,
                  reason: rejectReason || undefined,
                })
              }
              disabled={rejectMutation.isPending}
            >
              {rejectMutation.isPending ? "Rejecting..." : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SnoozedEmptyState({ count, onShow }: { count: number; onShow: () => void }) {
  return (
    <Card>
      <CardContent className="py-4">
        <PageEmptyState
          icon={<ClipboardCheck className="h-12 w-12" />}
          title={`${count} snoozed action${count === 1 ? "" : "s"}`}
          description="Hidden until their snooze ends."
          action={
            <Button variant="outline" size="sm" onClick={onShow}>
              Show snoozed
            </Button>
          }
        />
      </CardContent>
    </Card>
  );
}

function ActionEmptyState({ status }: { status: string }) {
  return (
    <Card>
      <CardContent className="py-4">
        <PageEmptyState
          icon={<ClipboardCheck className="h-12 w-12" />}
          title={status === "pending" ? "All caught up!" : "No actions"}
          description={
            status === "pending"
              ? "No pending actions to review. Approval requests from your AI agents appear here."
              : status === "all"
                ? "Approval requests from your AI agents appear here."
                : `Actions appear here once they are ${status}.`
          }
        />
      </CardContent>
    </Card>
  );
}

function ActionListSkeleton() {
  return (
    <Card>
      <CardContent className="py-4">
        <PageLoadingState message="Loading pending actions…" />
      </CardContent>
    </Card>
  );
}
