"use client";

import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import {
  dashboardApi,
  type TodayQueueItem,
  type TodayQueueKind,
} from "@/lib/api/dashboard";
import { queryKeys } from "@/lib/query-keys";
import { POLL_60S } from "@/lib/query-options";

/** How many kind-phrases the headline shows before collapsing the rest. */
const MAX_HEADLINE_PHRASES = 3;

const HEADLINE_PHRASES: Record<TodayQueueKind, (n: number) => string> = {
  replies_waiting: (n) => `${n} ${n === 1 ? "reply" : "replies"} waiting`,
  appointments_today: (n) => `${n} ${n === 1 ? "appointment" : "appointments"} today`,
  approvals: (n) => `${n} ${n === 1 ? "approval" : "approvals"} waiting`,
  hot_nudges: (n) => `${n} ${n === 1 ? "nudge" : "nudges"} due today`,
  prospect_batch: (n) => `${n} new ${n === 1 ? "lead" : "leads"} to review`,
  draft_campaign: (n) => `${n} draft ${n === 1 ? "campaign" : "campaigns"}`,
  setup_gap: (n) => `${n} setup ${n === 1 ? "step" : "steps"}`,
};

/**
 * Summarize the queue as one briefing sentence, e.g.
 * "3 replies waiting, 2 approvals waiting, 1 appointment today".
 * Phrases follow queue order; anything past the third collapses to "and N more".
 */
function buildHeadline(items: TodayQueueItem[]): string {
  const totals = new Map<TodayQueueKind, number>();
  for (const item of items) {
    // Draft campaigns and setup gaps are one row each — their `count` is
    // contacts enrolled, not actions to take.
    const quantity =
      item.kind === "draft_campaign" || item.kind === "setup_gap" ? 1 : item.count;
    totals.set(item.kind, (totals.get(item.kind) ?? 0) + quantity);
  }

  const phrases = Array.from(totals, ([kind, n]) => HEADLINE_PHRASES[kind](n));
  const visible = phrases.slice(0, MAX_HEADLINE_PHRASES);
  const hidden = phrases.length - visible.length;
  return hidden > 0 ? `${visible.join(", ")}, and ${hidden} more` : visible.join(", ");
}

export function TodayPage() {
  const workspaceId = useWorkspaceId();

  const {
    data: queue,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.dashboard.todayQueue(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return dashboardApi.getTodayQueue(workspaceId);
    },
    enabled: !!workspaceId,
    ...POLL_60S,
  });

  const items = queue?.items ?? [];
  const headline = items.length > 0 ? buildHeadline(items) : null;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Today</h1>
          {headline ? (
            <h2 className="mt-1 text-xl font-medium tracking-tight">{headline}</h2>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">Your morning briefing.</p>
          )}
        </div>
        <Button asChild>
          <Link href="/assistant?briefing=1">
            <Sparkles className="size-4" />
            Start my day
          </Link>
        </Button>
      </div>

      {isPending ? (
        <PageLoadingState message="Building today's queue…" />
      ) : isError ? (
        <PageErrorState
          message="We couldn't load today's queue. Please try again."
          onRetry={() => refetch()}
        />
      ) : items.length === 0 ? (
        <PageEmptyState
          title="All clear"
          description="Today's queue is empty. Tasks and approvals show up here as they come in."
          action={
            <Button asChild variant="outline">
              <Link href="/assistant?briefing=1">Ask the assistant anyway</Link>
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {items.length === 1 ? "1 item" : `${items.length} items`} — start at the top and
            work down.
          </p>
          <ol className="flex flex-col gap-3">
            {items.map((item, index) => (
              <li key={item.id}>
                <Card>
                  <CardContent className="flex flex-wrap items-center gap-4 p-4">
                    <div
                      aria-hidden="true"
                      className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-sm text-muted-foreground"
                    >
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{item.title}</p>
                      {item.body ? (
                        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                          {item.body}
                        </p>
                      ) : null}
                    </div>
                    {index === 0 ? (
                      <Button asChild className="shrink-0">
                        <Link href={item.href}>{item.cta_label}</Link>
                      </Button>
                    ) : (
                      <Link
                        href={item.href}
                        className="shrink-0 text-sm font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
                      >
                        {item.cta_label}
                      </Link>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
