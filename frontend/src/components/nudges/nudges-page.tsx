"use client";

import { Bell } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PageErrorState } from "@/components/ui/page-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { NudgeCard } from "./nudge-card";
import { STATUS_TABS } from "./nudge-presentation";
import { NudgeEmptyState, NudgeListSkeleton } from "./nudge-states";
import { NudgeStats } from "./nudge-stats";
import { useNudgesController } from "./use-nudges-controller";

// Re-exported so existing consumers/tests can keep importing the card from the
// page module after the container/presentational split.
export { NudgeCard };

export function NudgesPage() {
  const {
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
    act,
    dismiss,
    snooze,
    isActing,
    isDismissing,
  } = useNudgesController();

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Nudges</h1>
            <p className="text-sm text-muted-foreground">
              Relationship reminders and follow-up prompts
            </p>
          </div>
          {stats && stats.pending > 0 && (
            <div className="flex items-center gap-2 rounded-lg border bg-warning/10 px-4 py-2">
              <Bell className="h-5 w-5 text-warning" />
              <span className="text-sm font-medium">
                {stats.pending} pending nudge{stats.pending !== 1 && "s"}
              </span>
            </div>
          )}
        </div>

        {/* Stats Cards */}
        <NudgeStats stats={stats} isLoading={statsLoading} />

        {/* Filter Tabs + List */}
        <Tabs
          value={statusFilter}
          onValueChange={(v) => changeStatusFilter(v as typeof statusFilter)}
        >
          <TabsList>
            {STATUS_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
                {tab.value === "pending" && stats && stats.pending > 0 && (
                  <span className="ml-1.5 rounded-full bg-warning px-1.5 py-0.5 text-xs text-white">
                    {stats.pending}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>

          {STATUS_TABS.map((tab) => (
            <TabsContent key={tab.value} value={tab.value} className="mt-4">
              {listLoading ? (
                <NudgeListSkeleton />
              ) : listError ? (
                <PageErrorState
                  message="We couldn't load your nudges. Please try again."
                  onRetry={() => refetchList()}
                />
              ) : !nudgeList?.items.length ? (
                <NudgeEmptyState status={tab.value} />
              ) : (
                <div className="space-y-3">
                  {nudgeList.items.map((nudge) => (
                    <NudgeCard
                      key={nudge.id}
                      nudge={nudge}
                      onAct={(actionTaken) => act(nudge.id, actionTaken)}
                      onDismiss={() => dismiss(nudge.id)}
                      onSnooze={(date) => snooze(nudge.id, date)}
                      isActing={isActing}
                      isDismissing={isDismissing}
                    />
                  ))}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between pt-4">
                      <p className="text-sm text-muted-foreground">
                        Page {page} of {totalPages} ({nudgeList.total} nudge
                        {nudgeList.total !== 1 && "s"})
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page <= 1}
                          onClick={() => setPage((p) => p - 1)}
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page >= totalPages}
                          onClick={() => setPage((p) => p + 1)}
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
    </div>
  );
}
