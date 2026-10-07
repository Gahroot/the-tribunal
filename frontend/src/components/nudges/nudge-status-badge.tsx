// Presentational badge mapping a non-pending nudge status to a styled label.
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";

export function NudgeStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "sent":
      // Delivered to the operator, but the follow-up itself is still open.
      return (
        <StatusBadge dotClass="bg-warning" className="text-xs">
          Notified
        </StatusBadge>
      );
    case "acted":
      return (
        <StatusBadge dotClass="bg-success" className="text-xs">
          Done
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
