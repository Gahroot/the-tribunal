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
import type {
  NudgeListFilter,
  NudgeStats,
  NudgeStatus,
  SuggestedAction,
} from "@/types/nudge";

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

/**
 * Statuses that still need a human. "sent" only means the operator was
 * notified; the follow-up stays open until it is marked done or dismissed.
 * Mirrors ACTIVE_NUDGE_STATUSES in the backend model.
 */
export const ACTIVE_NUDGE_STATUSES: readonly NudgeStatus[] = ["pending", "sent"];

export const DEFAULT_NUDGE_FILTER: NudgeListFilter = "active";

export function isActiveNudgeStatus(status: NudgeStatus): boolean {
  return ACTIVE_NUDGE_STATUSES.includes(status);
}

export const STATUS_TABS: { value: NudgeListFilter; label: string }[] = [
  { value: "active", label: "Needs attention" },
  { value: "pending", label: "Not yet notified" },
  { value: "sent", label: "Notified" },
  { value: "snoozed", label: "Snoozed" },
  { value: "acted", label: "Done" },
  { value: "dismissed", label: "Dismissed" },
];

export const PAGE_SIZE = 20;

/** Unresolved nudges (pending + sent) — the count for badges and headers. */
export function activeNudgeCount(stats: NudgeStats | null | undefined): number {
  if (!stats) return 0;
  return stats.pending + stats.sent;
}

/** Count matching a list scope, so tab badges agree with the list totals. */
export function countForFilter(
  stats: NudgeStats | null | undefined,
  filter: NudgeListFilter,
): number {
  if (!stats) return 0;
  return filter === "active" ? activeNudgeCount(stats) : stats[filter];
}

const EMPTY_COPY: Record<NudgeListFilter, { title: string; description: string }> = {
  active: {
    title: "All caught up!",
    description:
      "Nothing needs your attention. Snoozed nudges come back here when their snooze ends; finished ones are under Done.",
  },
  pending: {
    title: "Nothing waiting to notify",
    description:
      "Every open nudge has already been sent to you. Notified ones still need follow-up under Needs attention.",
  },
  sent: {
    title: "No notified nudges open",
    description:
      "Nudges appear here after we text or push them to you, and stay until you mark them done or dismiss them.",
  },
  snoozed: {
    title: "No snoozed nudges",
    description: "Snoozed nudges return to Needs attention when their snooze date passes.",
  },
  acted: {
    title: "No completed nudges",
    description: "Nudges you mark as done show up here.",
  },
  dismissed: {
    title: "No dismissed nudges",
    description: "Nudges you dismiss show up here.",
  },
};

/**
 * Empty-state copy for a list scope. When the workspace has no nudges at all
 * (`hasAnyNudges === false`) explain where nudges come from instead.
 */
export function getNudgeEmptyCopy(
  filter: NudgeListFilter,
  hasAnyNudges: boolean | undefined,
): { title: string; description: string } {
  if (hasAnyNudges === false) {
    return {
      title: "No nudges yet",
      description:
        "When contacts have upcoming birthdays, go quiet, or need a follow-up, nudges will appear here.",
    };
  }
  return EMPTY_COPY[filter];
}

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
