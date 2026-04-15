"use client";

import { format } from "date-fns";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CalendarCheck2,
  Clock,
  PhoneCall,
  TrendingUp,
} from "lucide-react";

import { useContactEngagement } from "@/hooks/use-contact-engagement";
import { PageErrorState, PageLoadingState } from "@/components/ui/page-state";

interface EngagementSummaryProps {
  workspaceId: string;
  contactId: number;
}

interface RowProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  hint?: string;
}

function Row({ icon, label, value, hint }: RowProps) {
  return (
    <div className="flex items-center justify-between gap-3 px-2 py-1.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-muted-foreground">{icon}</span>
        <span>{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold">{value}</span>
        {hint ? (
          <span className="text-[10px] text-muted-foreground">{hint}</span>
        ) : null}
      </div>
    </div>
  );
}

export function EngagementSummary({
  workspaceId,
  contactId,
}: EngagementSummaryProps) {
  const { data, isLoading, isError, refetch } = useContactEngagement(
    workspaceId,
    contactId,
  );

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground px-2">
        Engagement
      </h3>
      {isLoading ? (
        <PageLoadingState className="min-h-[120px]" />
      ) : isError || !data ? (
        <PageErrorState
          className="min-h-[120px]"
          message="Couldn't load engagement stats."
          onRetry={() => {
            void refetch();
          }}
        />
      ) : (
        <div className="rounded-lg bg-muted/40 px-1 py-1 divide-y divide-border/40">
          <Row
            icon={<ArrowUpRight className="h-3.5 w-3.5" />}
            label="Sent"
            value={data.total_messages_sent}
          />
          <Row
            icon={<ArrowDownLeft className="h-3.5 w-3.5" />}
            label="Received"
            value={data.total_messages_received}
          />
          <Row
            icon={<PhoneCall className="h-3.5 w-3.5" />}
            label="Calls"
            value={data.total_calls}
            hint={
              data.total_calls > 0
                ? `${data.total_calls_answered} answered`
                : undefined
            }
          />
          <Row
            icon={<CalendarCheck2 className="h-3.5 w-3.5" />}
            label="Appointments"
            value={data.total_appointments}
          />
          <Row
            icon={<TrendingUp className="h-3.5 w-3.5" />}
            label="Last 7d / 30d"
            value={`${data.events_last_7d} / ${data.events_last_30d}`}
          />
          {data.last_activity_at ? (
            <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>
                Last activity:{" "}
                {format(new Date(data.last_activity_at), "MMM d, h:mm a")}
              </span>
            </div>
          ) : null}
          {data.channels_used.length > 0 ? (
            <div className="flex items-center gap-1.5 px-2 py-1.5 text-[10px] text-muted-foreground">
              <span>Channels:</span>
              {data.channels_used.map((c) => (
                <span
                  key={c}
                  className="rounded-full bg-background px-2 py-0.5 uppercase tracking-wide"
                >
                  {c}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
