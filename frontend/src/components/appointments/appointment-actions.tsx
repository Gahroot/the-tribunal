"use client";

import { Bell, Check, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { appointmentsApi } from "@/lib/api/appointments";
import { offsetToLabel } from "@/lib/calendar/calendar-derivations";
import type { Appointment } from "@/types";

interface ReminderBadgesProps {
  reminderSentAt?: string | null;
  remindersSent?: number[] | null;
  reminderOffsets?: number[] | null;
}

export function ReminderBadges({
  reminderSentAt,
  remindersSent,
  reminderOffsets,
}: ReminderBadgesProps) {
  const sent = remindersSent ?? [];

  // If we have reminder offsets (from agent data on appointment), show multi-badge
  if (reminderOffsets && reminderOffsets.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {reminderOffsets.map((offset) => {
          const fired = sent.includes(offset);
          return (
            <StatusBadge
              key={offset}
              dotClass={fired ? "bg-success" : "bg-muted-foreground"}
              className="text-[10px] py-0"
            >
              {offsetToLabel(offset)}
              {fired && <Check aria-hidden="true" className="size-2.5" />}
            </StatusBadge>
          );
        })}
      </div>
    );
  }

  // If we have fired reminders but no offset config, show fired ones
  if (sent.length > 0) {
    return (
      <div className="flex flex-wrap gap-1">
        {sent.map((offset) => (
          <StatusBadge
            key={offset}
            dotClass="bg-success"
            className="text-[10px] py-0"
          >
            {offsetToLabel(offset)}
            <Check aria-hidden="true" className="size-2.5" />
          </StatusBadge>
        ))}
      </div>
    );
  }

  // Legacy fallback: just reminder_sent_at set
  if (reminderSentAt) {
    return (
      <StatusBadge dotClass="bg-success" className="text-[10px] py-0">
        Reminder sent
      </StatusBadge>
    );
  }

  return null;
}

interface SyncButtonProps {
  appointment: Appointment;
  workspaceId: string;
  onSynced: () => void;
}

export function SyncButton({ appointment, workspaceId, onSynced }: SyncButtonProps) {
  const [isSyncing, setIsSyncing] = useState(false);

  if (appointment.sync_status !== "pending") return null;

  const handleSync = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsSyncing(true);
    try {
      const result = await appointmentsApi.syncAppointment(workspaceId, appointment.id);
      if (result.status === "synced") {
        toast.success("Synced to Cal.com");
        onSynced();
      } else {
        toast.error(`Sync failed: ${result.error ?? "Unknown error"}`);
      }
    } catch {
      toast.error("Failed to sync appointment");
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <Button
      variant="outline"
      size="sm"
      className="text-xs h-7 gap-1"
      onClick={handleSync}
      disabled={isSyncing}
      title="Sync to Cal.com"
    >
      {isSyncing ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <RefreshCw className="size-3" />
      )}
      Sync
    </Button>
  );
}

interface SendReminderButtonProps {
  appointment: Appointment;
  workspaceId: string;
  onSent: () => void;
}

export function SendReminderButton({
  appointment,
  workspaceId,
  onSent,
}: SendReminderButtonProps) {
  const [isSending, setIsSending] = useState(false);

  if (appointment.status !== "scheduled") return null;

  const handleSend = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsSending(true);
    try {
      const result = await appointmentsApi.sendReminder(workspaceId, appointment.id);
      if (result.success) {
        toast.success(`Reminder sent to ${result.sent_to ?? "contact"}`);
        onSent();
      } else {
        toast.error(result.message || "Failed to send reminder");
      }
    } catch {
      toast.error("Failed to send reminder");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <Button
      variant="outline"
      size="sm"
      className="text-xs h-7 gap-1"
      onClick={handleSend}
      disabled={isSending}
      title="Send SMS reminder"
    >
      {isSending ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <Bell className="size-3" />
      )}
      Remind
    </Button>
  );
}
