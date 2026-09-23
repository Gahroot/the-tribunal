import {
  ArrowDownLeft,
  ArrowUpRight,
  CalendarCheck,
  Mail,
  MessageSquare,
  Mic,
  Phone,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { useId } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDate, formatRelative } from "@/lib/utils/date";
import type { TimelineItem } from "@/types";

type TimelineKind = TimelineItem["type"];

const TYPE_LABELS: Partial<Record<TimelineKind, string>> = {
  sms: "SMS",
  call: "Call",
  email: "Email",
  voicemail: "Voicemail",
  appointment: "Appointment",
  note: "Note",
};

const TYPE_ICONS: Partial<Record<TimelineKind, LucideIcon>> = {
  sms: MessageSquare,
  call: Phone,
  email: Mail,
  voicemail: Mic,
  appointment: CalendarCheck,
  note: StickyNote,
};

function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

interface ContactActivityTimelineProps {
  timeline: TimelineItem[];
  className?: string;
}

/**
 * Chronological activity feed for the contact detail panel: every timeline
 * event with its type, direction, relative time, call duration, and booking
 * outcome. The sidebar timeline arrives oldest-first; newest renders on top.
 */
export function ContactActivityTimeline({ timeline, className }: ContactActivityTimelineProps) {
  // Unique per instance: ConversationLayout can mount the sidebar twice
  // (inline desktop + mobile sheet), so a static id would duplicate.
  const headingId = useId();
  const items = [...timeline].reverse();

  return (
    <section aria-labelledby={headingId} className={cn("space-y-2", className)}>
      <h3 id={headingId} className="px-2 text-sm font-medium text-muted-foreground">
        Activity timeline
      </h3>
      {items.length === 0 ? (
        <p className="px-2 text-sm text-muted-foreground">No activity yet.</p>
      ) : (
        <ol className="space-y-1.5 px-2">
          {items.map((item) => {
            const Icon = TYPE_ICONS[item.type] ?? MessageSquare;
            const label = TYPE_LABELS[item.type] ?? "Activity";
            return (
              <li
                key={item.id}
                className="flex items-start gap-2.5 rounded-lg border bg-card/60 p-2"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate text-xs font-medium">{label}</p>
                    {item.is_ai ? (
                      <Badge className="h-4 px-1 text-[10px] font-medium">AI</Badge>
                    ) : null}
                    {item.direction === "outbound" ? (
                      <ArrowUpRight
                        role="img"
                        aria-label="Outbound"
                        className="h-3 w-3 shrink-0 text-muted-foreground"
                      />
                    ) : item.direction === "inbound" ? (
                      <ArrowDownLeft
                        role="img"
                        aria-label="Inbound"
                        className="h-3 w-3 shrink-0 text-muted-foreground"
                      />
                    ) : null}
                  </div>
                  <p className="line-clamp-2 break-words text-xs text-muted-foreground">
                    {item.content}
                  </p>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
                    <time
                      dateTime={item.timestamp}
                      title={formatDate(item.timestamp, {
                        pattern: "MMM d, yyyy, h:mm a",
                      })}
                    >
                      {formatRelative(item.timestamp)}
                    </time>
                    {typeof item.duration_seconds === "number" && item.duration_seconds > 0 && (
                      <span>{formatDuration(item.duration_seconds)}</span>
                    )}
                    {item.booking_outcome === "success" ? (
                      <Badge className="h-4 px-1 text-[10px] font-medium">Booked</Badge>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
