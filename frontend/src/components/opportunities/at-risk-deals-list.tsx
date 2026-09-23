"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, KanbanSquare, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { queryKeys } from "@/lib/query-keys";
import { POLL_60S } from "@/lib/query-options";
import { formatCurrency } from "@/lib/utils/number";
import type { AtRiskDeal, DealHealthStatus } from "@/types";

const HEALTH_DOT: Record<DealHealthStatus, string> = {
  healthy: "bg-success",
  watch: "bg-warning",
  at_risk: "bg-warning",
  critical: "bg-destructive",
};

interface AtRiskDealsListProps {
  workspaceId: string;
  limit?: number;
  onSelect?: (opportunityId: string) => void;
}

export function AtRiskDealsList({
  workspaceId,
  limit = 25,
  onSelect,
}: AtRiskDealsListProps) {
  const {
    data,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.opportunities.atRisk(workspaceId, { limit }),
    queryFn: () => opportunitiesApi.listAtRisk(workspaceId, { limit }),
    enabled: !!workspaceId,
    ...POLL_60S,
  });

  // Distinguish "deals exist but all healthy" from "no deals at all" so the
  // empty state never falsely reassures a workspace that has zero opportunities.
  const { data: opportunitiesData } = useQuery({
    queryKey: queryKeys.opportunities.list(workspaceId, { page_size: 1 }),
    queryFn: () => opportunitiesApi.list(workspaceId, { page_size: 1 }),
    enabled: !!workspaceId,
  });
  const hasNoOpportunities = opportunitiesData?.total === 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          At-Risk Deals
        </CardTitle>
        {data && data.total > 0 && (
          <span className="text-sm text-muted-foreground">
            {formatCurrency(data.total_amount_at_risk)} at risk
          </span>
        )}
      </CardHeader>
      <CardContent>
        {isPending ? (
          <PageLoadingState message="Scoring deals…" />
        ) : isError ? (
          <PageErrorState
            message="Couldn't load at-risk deals."
            onRetry={() => void refetch()}
          />
        ) : !data.items.length ? (
          hasNoOpportunities ? (
            <PageEmptyState
              icon={<KanbanSquare className="h-10 w-10" />}
              title="No deals yet"
              description="There are no opportunities to coach. Create your first deal to start tracking pipeline health."
              action={
                <Button asChild size="sm">
                  <Link href="/opportunities">Create a deal</Link>
                </Button>
              }
            />
          ) : (
            <PageEmptyState
              icon={<ShieldCheck className="h-10 w-10" />}
              title="No deals at risk"
              description="Every open deal looks healthy right now."
            />
          )
        ) : (
          <ul className="divide-y">
            {data.items.map((deal) => (
              <AtRiskRow
                key={deal.opportunity_id}
                deal={deal}
                onSelect={onSelect}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function AtRiskRow({
  deal,
  onSelect,
}: {
  deal: AtRiskDeal;
  onSelect?: (opportunityId: string) => void;
}) {
  const content = (
    <>
      <div className="min-w-0 space-y-0.5 text-left">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{deal.name}</p>
          <StatusBadge dotClass={HEALTH_DOT[deal.deal_health]} className="text-xs">
            {deal.deal_health.replace("_", " ")}
          </StatusBadge>
        </div>
        <p className="truncate text-xs text-muted-foreground">{deal.top_risk}</p>
      </div>
      <div className="shrink-0 text-right">
        {deal.amount != null && (
          <p className="text-sm font-medium">
            {formatCurrency(deal.amount, deal.currency)}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Risk {deal.risk_score}/100
        </p>
      </div>
    </>
  );

  if (!onSelect) {
    return (
      <li className="flex items-center justify-between gap-3 py-3">{content}</li>
    );
  }

  return (
    <li>
      <button
        type="button"
        className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-md px-2 py-3 hover:bg-muted/50"
        onClick={() => onSelect(deal.opportunity_id)}
      >
        {content}
      </button>
    </li>
  );
}
