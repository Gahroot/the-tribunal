// Presentational nudge row. Stateless apart from the local snooze popover;
// all data actions are delegated to callbacks supplied by the container.
import {
  AlarmClock,
  ArrowRight,
  CalendarIcon,
  Check,
  Mail,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar-lazy";
import { Card, CardContent } from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { addDays, formatDayMonth } from "@/lib/utils/date";
import type { HumanNudge } from "@/types/nudge";

import {
  PRIORITY_STYLES,
  SUGGESTED_ACTION_LABELS,
  formatDueDate,
  getNudgeEmoji,
} from "./nudge-presentation";
import { NudgeStatusBadge } from "./nudge-status-badge";

export interface NudgeCardProps {
  nudge: HumanNudge;
  onAct: (actionTaken?: string) => void;
  onDismiss: () => void;
  onSnooze: (date: Date) => void;
  isActing: boolean;
  isDismissing: boolean;
}

export function NudgeCard({
  nudge,
  onAct,
  onDismiss,
  onSnooze,
  isActing,
  isDismissing,
}: NudgeCardProps) {
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const emoji = getNudgeEmoji(nudge.nudge_type);
  const isPending = nudge.status === "pending";

  return (
    <Card>
      <CardContent className="flex items-start gap-4 p-4">
        {/* Emoji icon */}
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-xl">
          {emoji}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-medium leading-tight">{nudge.title}</h3>
              <p className="text-sm text-muted-foreground line-clamp-2">
                {nudge.message}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Badge className={cn("text-xs", PRIORITY_STYLES[nudge.priority])}>
                {nudge.priority}
              </Badge>
              {nudge.suggested_action && (
                <Badge variant="outline" className="text-xs">
                  {SUGGESTED_ACTION_LABELS[nudge.suggested_action]}
                </Badge>
              )}
            </div>
          </div>

          {/* Contact + Due date row */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {nudge.contact_name && nudge.contact_id !== null && (
              <Link
                href={`/contacts/${nudge.contact_id}`}
                className="font-medium text-foreground hover:underline"
              >
                {nudge.contact_name}
                {nudge.contact_company && (
                  <span className="font-normal text-muted-foreground">
                    {" "}
                    · {nudge.contact_company}
                  </span>
                )}
              </Link>
            )}
            <span className="flex items-center gap-1">
              <CalendarIcon className="h-3 w-3" />
              {formatDueDate(nudge.due_date)}
            </span>
            {nudge.status === "snoozed" && nudge.snoozed_until && (
              <span className="flex items-center gap-1">
                <AlarmClock className="h-3 w-3" />
                Snoozed until {formatDayMonth(nudge.snoozed_until)}
              </span>
            )}
            {nudge.status !== "pending" && nudge.status !== "snoozed" && (
              <NudgeStatusBadge status={nudge.status} />
            )}
          </div>
        </div>

        {/* Actions */}
        {isPending && (
          <div className="flex shrink-0 items-center gap-1">
            {nudge.href ? (
              <Button asChild size="sm" title={nudge.cta_label ?? "Open"}>
                <Link href={nudge.href}>
                  <ArrowRight className="mr-1 h-3.5 w-3.5" />
                  {nudge.cta_label ?? "Open"}
                </Link>
              </Button>
            ) : nudge.suggested_action === "send_card" ? (
              <>
                <Button
                  size="sm"
                  onClick={() => onAct("send_card")}
                  disabled={isActing}
                  title="Send Card"
                >
                  <Mail className="mr-1 h-3.5 w-3.5" />
                  Send Card
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onAct()}
                  disabled={isActing}
                  title="Mark as done"
                >
                  <Check className="mr-1 h-3.5 w-3.5" />
                  Done
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onAct()}
                disabled={isActing}
                title="Mark as done"
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                Done
              </Button>
            )}

            <Popover open={snoozeOpen} onOpenChange={setSnoozeOpen}>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" title="Snooze">
                  <AlarmClock className="mr-1 h-3.5 w-3.5" />
                  Snooze
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="end">
                <div className="space-y-2 p-3">
                  <p className="text-sm font-medium">Snooze until</p>
                  <div className="flex flex-col gap-1">
                    {[
                      { label: "Tomorrow", days: 1 },
                      { label: "In 3 days", days: 3 },
                      { label: "Next week", days: 7 },
                    ].map((opt) => (
                      <Button
                        key={opt.days}
                        variant="ghost"
                        size="sm"
                        className="justify-start"
                        onClick={() => {
                          onSnooze(addDays(new Date(), opt.days));
                          setSnoozeOpen(false);
                        }}
                      >
                        {opt.label}
                      </Button>
                    ))}
                  </div>
                  <Calendar
                    mode="single"
                    disabled={(date) => date < new Date()}
                    onSelect={(date) => {
                      if (date) {
                        onSnooze(date);
                        setSnoozeOpen(false);
                      }
                    }}
                  />
                </div>
              </PopoverContent>
            </Popover>

            <Button
              size="sm"
              variant="ghost"
              onClick={onDismiss}
              disabled={isDismissing}
              title="Dismiss"
              className="text-muted-foreground hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
