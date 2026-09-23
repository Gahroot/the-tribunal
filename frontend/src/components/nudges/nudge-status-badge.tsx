// Presentational badge mapping a non-pending nudge status to a styled label.
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";

export function NudgeStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "sent":
      return (
        <StatusBadge dotClass="bg-muted-foreground" className="text-xs">
          Sent
        </StatusBadge>
      );
    case "acted":
      return (
        <StatusBadge dotClass="bg-success" className="text-xs">
          Acted
        </StatusBadge>
      );
    case "dismissed":
      return (
        <StatusBadge dotClass="bg-destructive" className="text-xs">
          Dismissed
        </StatusBadge>
      );
    default:
      return (
        <Badge variant="outline" className="text-xs">
          {status}
        </Badge>
      );
  }
}
