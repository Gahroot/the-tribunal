import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CampaignStatus } from "@/types";

const statusDotColors: Record<CampaignStatus, string> = {
  draft: "bg-muted-foreground",
  scheduled: "bg-blue-500",
  running: "bg-green-500",
  paused: "bg-yellow-500",
  completed: "bg-purple-500",
  cancelled: "bg-red-500",
};

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
        className={cn("size-1.5 shrink-0 rounded-full", statusDotColors[status])}
      />
      {statusLabels[status]}
    </Badge>
  );
}
