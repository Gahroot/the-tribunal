// Presentational empty + loading states for the Nudges list.
import { Inbox } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { PageEmptyState } from "@/components/ui/page-state";
import { Skeleton } from "@/components/ui/skeleton";
import type { NudgeListFilter } from "@/types/nudge";

import { getNudgeEmptyCopy } from "./nudge-presentation";

export function NudgeEmptyState({
  filter,
  hasAnyNudges,
}: {
  filter: NudgeListFilter;
  /** `false` only when stats confirm the workspace has no nudges at all. */
  hasAnyNudges?: boolean;
}) {
  const { title, description } = getNudgeEmptyCopy(filter, hasAnyNudges);
  return (
    <Card>
      <CardContent className="py-4">
        <PageEmptyState
          icon={<Inbox className="h-12 w-12" />}
          title={title}
          description={description}
        />
      </CardContent>
    </Card>
  );
}

export function NudgeListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="flex items-start gap-4 p-4">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-72" />
              <Skeleton className="h-3 w-32" />
            </div>
            <div className="flex gap-1">
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-8 w-18" />
              <Skeleton className="h-8 w-8" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
