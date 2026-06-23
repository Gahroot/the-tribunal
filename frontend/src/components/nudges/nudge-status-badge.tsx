// Presentational badge mapping a non-pending nudge status to a styled label.
import { Badge } from "@/components/ui/badge";

export function NudgeStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "sent":
      return (
        <Badge variant="secondary" className="text-xs">
          Sent
        </Badge>
      );
    case "acted":
      return (
        <Badge variant="default" className="bg-green-600 text-xs">
          Acted
        </Badge>
      );
    case "dismissed":
      return (
        <Badge variant="destructive" className="text-xs">
          Dismissed
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-xs">
          {status}
        </Badge>
      );
  }
}
