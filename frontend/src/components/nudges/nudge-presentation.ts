// Pure presentation helpers and lookup tables for the Nudges page. Free of
// React/JSX so the formatting + lookup rules can be unit-tested directly.
import {
  Cake,
  Heart,
  RefreshCw,
  CalendarDays,
  ClipboardList,
  Target,
  Package,
  Hourglass,
  Satellite,
  Pin,
  type LucideIcon,
} from "lucide-react";

import { formatRelative } from "@/lib/utils/date";
import type { NudgeStatus, SuggestedAction } from "@/types/nudge";

export const NUDGE_TYPE_ICONS: Record<string, LucideIcon> = {
  birthday: Cake,
  anniversary: Heart,
  cooling: RefreshCw,
  custom: CalendarDays,
  follow_up: ClipboardList,
  deal_milestone: Target,
  // Workspace-level operator nudges
  outbound_batch_ready: Package,
  approvals_waiting: Hourglass,
  monitor_idle: Satellite,
};

export const SUGGESTED_ACTION_LABELS: Record<SuggestedAction, string> = {
  send_card: "Send Card",
  call: "Call",
  text: "Text",
  email: "Email",
};

export const PRIORITY_DOTS: Record<string, string> = {
  high: "bg-destructive",
  medium: "bg-warning",
  low: "bg-muted-foreground",
};

export const STATUS_TABS: { value: NudgeStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "acted", label: "Acted" },
  { value: "dismissed", label: "Dismissed" },
  { value: "snoozed", label: "Snoozed" },
];

export const PAGE_SIZE = 20;

/** Icon for a nudge type, falling back to a generic pin. */
export function getNudgeIcon(nudgeType: string): LucideIcon {
  return NUDGE_TYPE_ICONS[nudgeType] ?? Pin;
}

/**
 * Human-friendly due-date label. Buckets the next/previous two weeks into
 * relative phrasing and defers to {@link formatRelative} beyond that. `now` is
 * injectable so the bucketing can be tested deterministically.
 */
export function formatDueDate(dateStr: string, now: Date = new Date()): string {
  const due = new Date(dateStr);
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  if (diffDays === -1) return "Yesterday";
  if (diffDays > 0 && diffDays <= 14) return `In ${diffDays} days`;
  if (diffDays < 0 && diffDays >= -14) return `${Math.abs(diffDays)} days ago`;

  return formatRelative(due);
}
