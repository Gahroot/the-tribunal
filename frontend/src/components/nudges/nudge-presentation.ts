// Pure presentation helpers and lookup tables for the Nudges page. Free of
// React/JSX so the formatting + lookup rules can be unit-tested directly.
import { formatRelative } from "@/lib/utils/date";
import type { NudgeStatus, SuggestedAction } from "@/types/nudge";

export const NUDGE_TYPE_EMOJI: Record<string, string> = {
  birthday: "🎂",
  anniversary: "💍",
  cooling: "🔄",
  custom: "📅",
  follow_up: "📋",
  deal_milestone: "🎯",
  // Workspace-level operator nudges
  outbound_batch_ready: "📦",
  approvals_waiting: "⏳",
  monitor_idle: "🛰️",
};

export const SUGGESTED_ACTION_LABELS: Record<SuggestedAction, string> = {
  send_card: "Send Card",
  call: "Call",
  text: "Text",
  email: "Email",
};

export const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
};

export const STATUS_TABS: { value: NudgeStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "acted", label: "Acted" },
  { value: "dismissed", label: "Dismissed" },
  { value: "snoozed", label: "Snoozed" },
];

export const PAGE_SIZE = 20;

/** Emoji for a nudge type, falling back to a generic pin. */
export function getNudgeEmoji(nudgeType: string): string {
  return NUDGE_TYPE_EMOJI[nudgeType] ?? "📌";
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
