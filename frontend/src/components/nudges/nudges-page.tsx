"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { PageErrorState } from "@/components/ui/page-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";

import { NudgeCard } from "./nudge-card";
import { STATUS_TABS, activeNudgeCount, countForFilter } from "./nudge-presentation";
import { NudgeEmptyState, NudgeListSkeleton } from "./nudge-states";
import { useNudgesController } from "./use-nudges-controller";

// Re-exported so existing consumers/tests can keep importing the card from the
// page module after the container/presentational split.
export { NudgeCard };

export function NudgesPage() {
  const workspaceId = useWorkspaceId();
  const search = useSearchParams();
  const rawContactId = search.get("contact_id");
  const contactId = rawContactId === null ? undefined : Number(rawContactId);
  // A stale bookmark must never apply another brand's contact to this brand.
  if (
    rawContactId !== null &&
    (!Number.isSafeInteger(contactId) ||
      (contactId ?? 0) <= 0 ||
      search.get("workspace_id") !== workspaceId)
  ) {
    return (
      <div className="p-6">
        <p>This contact backlog is not available in the current brand.</p>
        <Link href="/nudges" className="text-sm underline">
          Open this brand&apos;s Inbox
        </Link>
      </div>
    );
  }
  return <NudgesList key={`${workspaceId}:${contactId ?? "all"}`} contactId={contactId} />;
}

function NudgesList({ contactId }: { contactId?: number }) {
  const {
    stats,
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
  } = useNudgesController(contactId);

  const openCount =
    contactId === undefined
      ? activeNudgeCount(stats)
      : statusFilter === "active"
        ? (nudgeList?.total ?? 0)
        : 0;
  // Only claim the workspace is truly empty once stats confirm it.
  const hasAnyNudges = contactId === undefined && stats ? stats.total > 0 : undefined;

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
            <p className="text-sm text-muted-foreground">
              {contactId === undefined
                ? "Relationship reminders and follow-up prompts"
                : `Tasks for contact #${contactId}`}
            </p>
            {contactId !== undefined && (
              <Link href={`/contacts/${contactId}`} className="text-sm underline">
                Back to contact
              </Link>
            )}
          </div>
          {openCount > 0 && (
            <div className="flex items-center gap-2 rounded-full border bg-muted px-3 py-1">
              <span aria-hidden className="size-2 rounded-full bg-warning" />
              <span className="text-sm font-medium text-muted-foreground">
                {openCount === 1 ? "1 nudge needs attention" : `${openCount} nudges need attention`}
              </span>
            </div>
          )}
        </div>

        {/* Filter Tabs + List */}
        <Tabs
          value={statusFilter}
          onValueChange={(v) => changeStatusFilter(v as typeof statusFilter)}
        >
          <TabsList>
            {STATUS_TABS.map((tab) => {
              const count = contactId === undefined ? countForFilter(stats, tab.value) : 0;
              return (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                  {tab.value === "active" && count > 0 && (
                    <span className="ml-1.5 rounded-full bg-warning px-1.5 py-0.5 text-xs text-white">
                      {count}
                    </span>
                  )}
                </TabsTrigger>
              );
            })}
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
                <NudgeEmptyState filter={tab.value} hasAnyNudges={hasAnyNudges} />
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
