"use client";

import { format } from "date-fns";
import { Clock, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Contact, TimelineItem } from "@/types";

interface ContactTimelineProps {
  contact: Contact;
  timeline: TimelineItem[];
}

export function ContactTimeline({ contact, timeline }: ContactTimelineProps) {
  const callCount = timeline.filter((t) => t.type === "call").length;
  const messageCount = timeline.filter((t) => t.type === "sms").length;
  const bookingCount = timeline.filter((t) => t.booking_outcome === "success").length;
  const lastActivity = timeline[timeline.length - 1];

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground px-2">Activity</h3>
      <div className="grid grid-cols-3 gap-3 px-2">
        <div className="bg-muted/50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold">{callCount}</p>
          <p className="text-xs text-muted-foreground">Calls</p>
        </div>
        <div className="bg-muted/50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold">{messageCount}</p>
          <p className="text-xs text-muted-foreground">Messages</p>
        </div>
        <div className="bg-muted/50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold text-success">{bookingCount}</p>
          <p className="text-xs text-muted-foreground">Booked</p>
        </div>
      </div>
      {lastActivity && (
        <div className="flex items-center gap-2 px-2 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>
            Last activity: {format(new Date(lastActivity.timestamp), "MMM d, h:mm a")}
          </span>
        </div>
      )}
      {(!!contact.noshow_count || contact.last_appointment_status) && (
        <div className="flex items-center gap-2 px-2 flex-wrap">
          {!!contact.noshow_count && contact.noshow_count > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-warning">
              <AlertTriangle className="h-3 w-3" />
              <span>
                {contact.noshow_count} no-show{contact.noshow_count !== 1 ? "s" : ""}
              </span>
            </div>
          )}
          {contact.last_appointment_status && (
            <Badge
              variant={
                contact.last_appointment_status === "no_show"
                  ? "destructive"
                  : contact.last_appointment_status === "completed"
                    ? "default"
                    : "secondary"
              }
              className="text-xs"
            >
              Last: {contact.last_appointment_status.replace(/_/g, " ")}
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
