import { Badge } from "@/components/ui/badge";
import { campaignStatusDotColors } from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import type { CampaignStatus } from "@/types";

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
  className,
}: {
  status: CampaignStatus;
  className?: string;
}) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", className)}>
      <span
        aria-hidden="true"
        className={cn("size-1.5 shrink-0 rounded-full", campaignStatusDotColors[status])}
      />
      {statusLabels[status]}
    </Badge>
  );
}
