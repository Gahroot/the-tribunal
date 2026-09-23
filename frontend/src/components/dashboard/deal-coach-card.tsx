"use client";

import { AlertTriangle, ArrowUpRight, ShieldAlert, Target } from "lucide-react";
import Link from "next/link";
import { memo } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import type { DealCoachStats } from "@/lib/api/dashboard";
import { formatCurrency } from "@/lib/utils/number";

interface DealCoachCardProps {
  dealCoachStats: DealCoachStats | undefined;
  isPending: boolean;
}

const HEALTH_DOTS: Record<string, string> = {
  critical: "bg-destructive",
  at_risk: "bg-warning",
  watch: "bg-info",
  healthy: "bg-success",
};

function healthLabel(health: string): string {
  return health.replace(/_/g, " ");
}

export const DealCoachCard = memo(function DealCoachCard({
  dealCoachStats,
  isPending,
}: DealCoachCardProps) {
  const topDeals = dealCoachStats?.top_deals ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 gradient-heading">
            <ShieldAlert className="size-5" />
            Deal Coach
          </CardTitle>
          <CardDescription>Pipeline health and next-best actions</CardDescription>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/deal-coach">
            Open Coach
            <ArrowUpRight className="ml-2 size-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {isPending && !dealCoachStats ? (
            <>
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="space-y-1 text-center">
                  <Skeleton className="mx-auto h-8 w-12" />
                  <Skeleton className="mx-auto h-3 w-16" />
                  <Skeleton className="mx-auto h-3 w-20" />
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-destructive">
                  <AlertTriangle className="size-4" />
                  <span className="text-2xl font-bold">
                    {dealCoachStats?.critical_count ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">Critical</p>
                <p className="text-xs text-muted-foreground">Deals</p>
              </div>

              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-warning">
                  <AlertTriangle className="size-4" />
                  <span className="text-2xl font-bold">
                    {dealCoachStats?.at_risk_count ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">At Risk</p>
                <p className="text-xs text-muted-foreground">Deals</p>
              </div>

              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-primary">
                  <Target className="size-4" />
                  <span className="text-2xl font-bold">
                    {dealCoachStats?.next_best_action_count ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">Next Actions</p>
                <p className="text-xs text-muted-foreground">Recommended</p>
              </div>

              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-destructive">
                  <span className="text-2xl font-bold">
                    {dealCoachStats
                      ? formatCurrency(
                          dealCoachStats.total_amount_at_risk,
                          dealCoachStats.currency,
                        )
                      : "—"}
                  </span>
                </div>
                <p className="text-xs font-medium">At Risk</p>
                <p className="text-xs text-muted-foreground">
                  of {dealCoachStats?.open_deals ?? 0} open
                </p>
              </div>
            </>
          )}
        </div>

        {dealCoachStats && topDeals.length > 0 && (
          <div className="space-y-2">
            {topDeals.map((deal) => (
              <div
                key={deal.opportunity_id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{deal.name}</span>
                    <StatusBadge
                      dotClass={HEALTH_DOTS[deal.deal_health] ?? "bg-muted-foreground"}
                      className="text-xs"
                    >
                      {healthLabel(deal.deal_health)}
                    </StatusBadge>
                  </div>
                  <p className="truncate text-sm text-muted-foreground">
                    {deal.top_risk}
                  </p>
                </div>
                <span className="shrink-0 text-sm font-semibold text-destructive">
                  {formatCurrency(deal.amount_at_risk, deal.currency)}
                </span>
              </div>
            ))}
          </div>
        )}

        {dealCoachStats && topDeals.length === 0 && (
          <p className="py-2 text-center text-sm text-muted-foreground">
            No at risk deals. Your pipeline is healthy.
          </p>
        )}
      </CardContent>
    </Card>
  );
});
