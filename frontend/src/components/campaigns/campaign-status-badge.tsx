import { Badge } from "@/components/ui/badge";
import { futureCampaignStart } from "@/lib/campaign-schedule";
import { campaignStatusDotColors } from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import type { Campaign, CampaignStatus } from "@/types";

const statusLabels: Record<CampaignStatus, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  cancelled: "Cancelled",
};

/**
 * Campaign status for list rows: neutral outline badge with a solid status
 * dot instead of a tinted-background/tinted-text pair.
 */
export function CampaignStatusBadge({
  status,
  schedule,
  className,
}: {
  status: CampaignStatus;
  schedule?: Campaign;
  className?: string;
}) {
  const start = schedule ? futureCampaignStart(schedule) : null;
  const displayStatus = start ? "scheduled" : status;
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Badge variant="outline" className={cn("gap-1.5", className)}>
        <span
          aria-hidden="true"
          className={cn("size-1.5 shrink-0 rounded-full", campaignStatusDotColors[displayStatus])}
        />
        {statusLabels[displayStatus]}
      </Badge>
      {start && <span className="text-xs text-muted-foreground">{start}</span>}
    </span>
  );
}
