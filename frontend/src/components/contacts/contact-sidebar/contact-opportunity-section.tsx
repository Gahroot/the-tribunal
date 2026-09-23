import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useId } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { STATIC } from "@/lib/query-options";
import { opportunityStatusColors } from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatCurrency } from "@/lib/utils/number";
import type { OpportunityStatus } from "@/types";

const OPPORTUNITY_STATUSES: OpportunityStatus[] = ["open", "won", "lost", "abandoned"];

interface ContactOpportunitySectionProps {
  workspaceId: string;
  contactId: number;
}

/**
 * Deal state for the contact detail panel. Mirrors the inbox context panel:
 * the opportunities list has no contact filter, so fetch one page and filter
 * client-side by primary contact — same query key, so both views share cache.
 */
export function ContactOpportunitySection({
  workspaceId,
  contactId,
}: ContactOpportunitySectionProps) {
  const headingId = useId();
  const queryClient = useQueryClient();

  const { data: opportunitiesData, isPending } = useQuery({
    queryKey: queryKeys.opportunities.list(workspaceId, {
      page: 1,
      page_size: 100,
    }),
    queryFn: () => opportunitiesApi.list(workspaceId, { page: 1, page_size: 100 }),
    enabled: !!workspaceId && contactId > 0,
    ...STATIC,
  });

  const { data: pipelines } = useQuery({
    queryKey: queryKeys.opportunities.pipelines(workspaceId),
    queryFn: () => opportunitiesApi.listPipelines(workspaceId),
    enabled: !!workspaceId && contactId > 0,
    ...STATIC,
  });

  const stageNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const pipeline of pipelines ?? []) {
      for (const stage of pipeline.stages ?? []) {
        map.set(stage.id, stage.name);
      }
    }
    return map;
  }, [pipelines]);

  const contactOpportunities = useMemo(
    () =>
      (opportunitiesData?.items ?? []).filter(
        (opportunity) => opportunity.primary_contact_id === contactId,
      ),
    [opportunitiesData?.items, contactId],
  );

  const updateStatusMutation = useMutation({
    mutationFn: (variables: { opportunityId: string; status: OpportunityStatus }) =>
      opportunitiesApi.update(workspaceId, variables.opportunityId, {
        status: variables.status,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(workspaceId),
      });
      toast.success(messages.opportunities.statusUpdated);
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, messages.opportunities.statusUpdateFailed));
    },
  });

  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <h3 id={headingId} className="px-2 text-sm font-medium text-muted-foreground">
        Opportunity
      </h3>
      {isPending ? (
        <div className="space-y-2 px-2">
          <Skeleton className="h-14 w-full rounded-lg" />
        </div>
      ) : contactOpportunities.length === 0 ? (
        <p className="px-2 text-sm text-muted-foreground">
          No opportunities linked to this contact.
        </p>
      ) : (
        contactOpportunities.map((opportunity) => {
          const stageName = opportunity.stage_id ? stageNames.get(opportunity.stage_id) : undefined;
          return (
            <div key={opportunity.id} className="mx-2 space-y-2 rounded-lg border p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{opportunity.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {stageName ?? "No stage"} · {opportunity.probability}%
                  </p>
                </div>
                {typeof opportunity.amount === "number" ? (
                  <span className="shrink-0 text-sm font-medium tabular-nums">
                    {formatCurrency(opportunity.amount, opportunity.currency)}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px] capitalize",
                    opportunityStatusColors[opportunity.status],
                  )}
                >
                  {opportunity.status}
                </Badge>
                <Select
                  value={opportunity.status}
                  onValueChange={(value) =>
                    updateStatusMutation.mutate({
                      opportunityId: opportunity.id,
                      status: value as OpportunityStatus,
                    })
                  }
                  disabled={updateStatusMutation.isPending}
                >
                  <SelectTrigger
                    className="h-7 w-[132px] text-xs"
                    aria-label={`Update status for ${opportunity.name}`}
                  >
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    {OPPORTUNITY_STATUSES.map((status) => (
                      <SelectItem key={status} value={status}>
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}
